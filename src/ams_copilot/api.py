from contextlib import asynccontextmanager
from dataclasses import asdict
from secrets import compare_digest
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ams_copilot.agents import AgentError
from ams_copilot.config import get_settings
from ams_copilot.guardrails import BudgetExceededError
from ams_copilot.models import Description, Identifier, KbArticle, QueryText, ReportDays, Ticket, Title, TriageOutcome
from ams_copilot.pipeline import Container, build_container


class TicketIn(BaseModel):
    tenant: Identifier
    title: Title
    description: Description
    id: Identifier | None = None
    reporter: str | None = None


class ArticleIn(BaseModel):
    ticket: TicketIn
    resolution_notes: str = Field(min_length=5, max_length=20000)
    root_cause: str | None = Field(default=None, max_length=10000)
    transactions: list[Identifier] = Field(default_factory=list, max_length=100)


class SearchIn(BaseModel):
    query: QueryText
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
    state = {"container": container}
    lock = Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if container is None and state["container"] is not None:
                state["container"].close()
                state["container"] = None

    app = FastAPI(title="AMS Copilot", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(BudgetExceededError)
    async def budget_error(request, error):
        return JSONResponse(status_code=429, content={"detail": str(error)})

    @app.exception_handler(AgentError)
    async def agent_error(request, error):
        return JSONResponse(status_code=502, content={"detail": "O provedor não concluiu a análise."})

    def current() -> Container:
        with lock:
            if state["container"] is None:
                state["container"] = build_container(get_settings())
        return state["container"]

    def identity(authorization: str | None = Header(default=None)) -> str | None:
        settings = container.settings if container is not None else get_settings()
        if not settings.tenant_api_keys:
            return None
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() == "bearer":
            for tenant, secret in settings.tenant_api_keys.items():
                if compare_digest(token.encode(), secret.get_secret_value().encode()):
                    return tenant
        raise HTTPException(status_code=401, detail="Credencial inválida", headers={"WWW-Authenticate": "Bearer"})

    def authorize(tenant: str, principal: str | None) -> None:
        if principal is not None and tenant != principal:
            raise HTTPException(status_code=403, detail="Cliente não autorizado")

    @app.get("/health")
    def health() -> dict[str, Any]:
        c = current()
        return {"status": "ok", "llm_model": c.llm.model, "kb_chunks": c.knowledge_base.store.count()}

    @app.post("/v1/tickets/triage", response_model=TriageOutcome)
    def triage(payload: TicketIn, principal: str | None = Depends(identity)) -> TriageOutcome:
        authorize(payload.tenant, principal)
        return current().pipeline.run(_ticket(payload))

    @app.post("/v1/kb/search")
    def search(payload: SearchIn, principal: str | None = Depends(identity)) -> list[dict[str, Any]]:
        hits = current().knowledge_base.search(payload.query, payload.top_k, payload.module)
        return [hit.as_dict() for hit in hits]

    @app.post("/v1/kb/articles", response_model=KbArticle)
    def draft_article(payload: ArticleIn, principal: str | None = Depends(identity)) -> KbArticle:
        authorize(payload.ticket.tenant, principal)
        return current().pipeline.draft_article(
            _ticket(payload.ticket), payload.resolution_notes, payload.root_cause, payload.transactions
        )

    @app.get("/v1/tickets/{ticket_id}/audit")
    def audit_trail(ticket_id: str, principal: str | None = Depends(identity)) -> list[dict[str, Any]]:
        events = current().audit.events(ticket_id, principal)
        if not events:
            raise HTTPException(status_code=404, detail="nenhum evento para este chamado")
        return events

    @app.get("/v1/tenants/{tenant}/usage")
    def usage(tenant: str, days: ReportDays = 30, principal: str | None = Depends(identity)) -> dict[str, Any]:
        authorize(tenant, principal)
        return current().audit.usage_report(tenant, days)

    @app.get("/v1/tenants/{tenant}/recurrence")
    def recurrence(tenant: str, principal: str | None = Depends(identity)) -> list[dict[str, Any]]:
        authorize(tenant, principal)
        return [asdict(cluster) for cluster in current().history.recurrence(tenant)]

    return app


app = create_app()
