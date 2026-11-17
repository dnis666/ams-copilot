import time
from dataclasses import dataclass
from typing import Any

from ams_copilot.agents import (
    AgentError,
    DiagnosisAgent,
    DocumentationAgent,
    ReviewerAgent,
    RunRecorder,
    TriageAgent,
)
from ams_copilot.audit import AuditStore
from ams_copilot.config import Settings
from ams_copilot.guardrails import decide_route, enforce_budget, ground_citations, mask_pii
from ams_copilot.llm import LLMClient, build_llm
from ams_copilot.models import Citation, Diagnosis, KbArticle, Review, Ticket, TriageOutcome
from ams_copilot.rag import (
    InMemoryVectorStore,
    KnowledgeBase,
    PgVectorStore,
    TicketHistory,
    VectorStore,
    build_embedder,
    load_documents,
)
from ams_copilot.tools import ToolRegistry


@dataclass
class Container:
    settings: Settings
    llm: LLMClient
    knowledge_base: KnowledgeBase
    history: TicketHistory
    audit: AuditStore

    @property
    def pipeline(self) -> "TriagePipeline":
        return TriagePipeline(self)


def build_container(settings: Settings, llm: LLMClient | None = None, audit: AuditStore | None = None) -> Container:
    embedder = build_embedder(settings)
    store: VectorStore = (
        PgVectorStore(settings.database_url, embedder.dimensions) if settings.database_url else InMemoryVectorStore()
    )
    knowledge_base = KnowledgeBase(store, embedder)
    if store.count() == 0 and settings.knowledge_base_dir.exists():
        knowledge_base.index(load_documents(settings.knowledge_base_dir))
    return Container(
        settings=settings,
        llm=llm or build_llm(settings),
        knowledge_base=knowledge_base,
        history=TicketHistory.from_jsonl(settings.tickets_history_path, embedder),
        audit=audit or AuditStore(settings.audit_db_path),
    )


class TriagePipeline:
    def __init__(self, container: Container) -> None:
        self.container = container
        self.settings = container.settings

    def _recorder(self, ticket: Ticket) -> RunRecorder:
        return RunRecorder(self.container.audit, ticket.tenant, ticket.id, self.settings.price_table)

    def _tools(self, tenant: str, retrieved: dict[str, Citation]) -> ToolRegistry:
        knowledge_base = self.container.knowledge_base
        history = self.container.history
        settings = self.settings

        def search_knowledge_base(query: str, module: str | None = None) -> dict[str, Any]:
            hits = knowledge_base.search(
                query, top_k=settings.retrieval_top_k, module=module, min_score=settings.retrieval_min_score
            )
            for hit in hits:
                retrieved.setdefault(
                    hit.chunk.doc_id,
                    Citation(doc_id=hit.chunk.doc_id, title=hit.chunk.title, score=round(hit.score, 4)),
                )
            return {
                "results": [
                    {
                        "doc_id": hit.chunk.doc_id,
                        "title": hit.chunk.title,
                        "module": hit.chunk.module,
                        "score": round(hit.score, 4),
                        "transactions": hit.chunk.metadata.get("transactions", []),
                        "content": hit.chunk.content,
                    }
                    for hit in hits
                ]
            }

        def find_similar_tickets(query: str) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "ticket_id": ticket.ticket_id,
                        "title": ticket.title,
                        "root_cause": ticket.root_cause,
                        "resolution": ticket.resolution,
                        "score": round(score, 4),
                    }
                    for ticket, score in history.similar(query, tenant)
                ]
            }

        registry = ToolRegistry()
        registry.register(
            "search_knowledge_base",
            "Busca artigos da base de conhecimento de AMS SAP por similaridade semântica.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Sintoma ou erro descrito no chamado"},
                    "module": {"type": "string", "description": "Módulo SAP para priorizar na busca"},
                },
                "required": ["query"],
            },
            search_knowledge_base,
        )
        registry.register(
            "find_similar_tickets",
            "Busca chamados já resolvidos do mesmo cliente com sintomas parecidos.",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Sintoma ou erro descrito no chamado"}},
                "required": ["query"],
            },
            find_similar_tickets,
        )
        return registry

    def run(self, ticket: Ticket) -> TriageOutcome:
        started = time.perf_counter()
        audit = self.container.audit
        llm = self.container.llm
        settings = self.settings

        remaining = enforce_budget(audit, ticket.tenant, settings.daily_token_budget_per_tenant)
        title, title_pii = mask_pii(ticket.title)
        description, description_pii = mask_pii(ticket.description)
        pii = {key: title_pii.get(key, 0) + description_pii.get(key, 0) for key in {*title_pii, *description_pii}}
        safe_ticket = {"id": ticket.id, "title": title, "description": description}

        recorder = self._recorder(ticket)
        recorder.event("pipeline", "ticket_received", {"pii_masked": pii, "token_budget_remaining": remaining})

        triage = TriageAgent(llm, recorder, max_steps=2).run({"ticket": safe_ticket})

        retrieved: dict[str, Citation] = {}
        tools = self._tools(ticket.tenant, retrieved)
        diagnosis: Diagnosis | None
        try:
            diagnosis = DiagnosisAgent(llm, recorder, tools, settings.max_agent_steps).run(
                {"ticket": safe_ticket, "triage": triage.model_dump(mode="json")}
            )
        except AgentError:
            diagnosis = None

        ungrounded = ground_citations(diagnosis, set(retrieved)) if diagnosis else []
        if ungrounded:
            recorder.event("guardrail", "citations_removed", {"doc_ids": ungrounded})

        try:
            review = ReviewerAgent(llm, recorder, max_steps=2).run(
                {
                    "ticket": safe_ticket,
                    "diagnosis": diagnosis.model_dump(mode="json") if diagnosis else None,
                    "sources": sorted(retrieved),
                }
            )
        except AgentError:
            review = Review(approved=False, issues=["Revisor não concluiu a análise."])

        route, reasons = decide_route(triage, diagnosis, review, settings.confidence_threshold, ungrounded)
        similar = [item.ticket_id for item, _ in self.container.history.similar(ticket.text, ticket.tenant)]
        cited = [retrieved[doc] for doc in (diagnosis.citations if diagnosis else []) if doc in retrieved]
        outcome = TriageOutcome(
            ticket_id=ticket.id,
            tenant=ticket.tenant,
            triage=triage,
            diagnosis=diagnosis,
            review=review,
            citations=cited,
            similar_tickets=similar,
            route=route,
            reasons=reasons,
            usage=recorder.usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        recorder.event(
            "pipeline",
            "decision",
            {
                "route": route,
                "reasons": reasons,
                "usage": recorder.usage.model_dump(),
                "latency_ms": outcome.latency_ms,
            },
        )
        return outcome

    def draft_article(
        self,
        ticket: Ticket,
        resolution_notes: str,
        root_cause: str | None = None,
        transactions: list[str] | None = None,
    ) -> KbArticle:
        recorder = self._recorder(ticket)
        title, _ = mask_pii(ticket.title)
        description, _ = mask_pii(ticket.description)
        notes, _ = mask_pii(resolution_notes)
        return DocumentationAgent(self.container.llm, recorder, max_steps=2).run(
            {
                "ticket": {"id": ticket.id, "title": title, "description": description},
                "resolution_notes": notes,
                "root_cause": root_cause,
                "transactions": transactions or [],
            }
        )
