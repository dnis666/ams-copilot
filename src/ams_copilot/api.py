from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ams_copilot.config import get_settings
from ams_copilot.guardrails import BudgetExceededError
from ams_copilot.models import KbArticle, Ticket, TriageOutcome
from ams_copilot.pipeline import Container, build_container


class TicketIn(BaseModel):
    tenant: str
    title: str = Field(min_length=3)
    description: str = Field(min_length=3)
    id: str | None = None
    reporter: str | None = None


class ArticleIn(BaseModel):
    ticket: TicketIn
    resolution_notes: str = Field(min_length=5)
    root_cause: str | None = None
    transactions: list[str] = Field(default_factory=list)


class SearchIn(BaseModel):
    query: str = Field(min_length=3)
    module: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)


def _ticket(payload: TicketIn) -> Ticket:
    return Ticket(
        id=payload.id or f"TCK-{uuid4().hex[:8].upper()}",
        tenant=payload.tenant,
        title=payload.title,
        description=payload.description,
        reporter=payload.reporter,
    )


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(title="AMS Copilot", version="0.1.0")
    state = {"container": container}

    def current() -> Container:
        if state["container"] is None:
            state["container"] = build_container(get_settings())
        return state["container"]

    @app.get("/health")
    def health() -> dict[str, Any]:
        c = current()
        return {"status": "ok", "llm_model": c.llm.model, "kb_chunks": c.knowledge_base.store.count()}

    @app.post("/v1/tickets/triage", response_model=TriageOutcome)
    def triage(payload: TicketIn) -> TriageOutcome:
        try:
            return current().pipeline.run(_ticket(payload))
        except BudgetExceededError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error

    @app.post("/v1/kb/search")
    def search(payload: SearchIn) -> list[dict[str, Any]]:
        hits = current().knowledge_base.search(payload.query, payload.top_k, payload.module)
        return [hit.as_dict() for hit in hits]

    @app.post("/v1/kb/articles", response_model=KbArticle)
    def draft_article(payload: ArticleIn) -> KbArticle:
        return current().pipeline.draft_article(
            _ticket(payload.ticket), payload.resolution_notes, payload.root_cause, payload.transactions
        )

    @app.get("/v1/tickets/{ticket_id}/audit")
    def audit_trail(ticket_id: str) -> list[dict[str, Any]]:
        events = current().audit.events(ticket_id)
        if not events:
            raise HTTPException(status_code=404, detail="nenhum evento para este chamado")
        return events

    @app.get("/v1/tenants/{tenant}/usage")
    def usage(tenant: str, days: int = 30) -> dict[str, Any]:
        return current().audit.usage_report(tenant, days)

    @app.get("/v1/tenants/{tenant}/recurrence")
    def recurrence(tenant: str) -> list[dict[str, Any]]:
        return [asdict(cluster) for cluster in current().history.recurrence(tenant)]

    return app


app = create_app()
