from pathlib import Path

from fastapi.testclient import TestClient

from ams_copilot.api import create_app
from ams_copilot.evaluation import evaluate, load_cases
from ams_copilot.models import Ticket
from ams_copilot.pipeline import Container

ROOT = Path(__file__).resolve().parents[1]


def ticket(**overrides) -> Ticket:
    data = {
        "id": "T-100",
        "tenant": "cliente-alfa",
        "title": "Pedidos do portal parados",
        "description": "IDoc ORDERS em status 51, material sem centro. Contato ana@cliente.com.br CPF 123.456.789-09",
    }
    data.update(overrides)
    return Ticket(**data)


def test_pipeline_triages_diagnoses_and_cites_sources(container: Container):
    outcome = container.pipeline.run(ticket())
    assert outcome.triage.module.value == "INTEGRATION"
    assert outcome.diagnosis is not None
    assert outcome.diagnosis.citations == ["KB-001"]
    assert outcome.citations[0].doc_id == "KB-001"
    assert "BD87" in outcome.diagnosis.sap_transactions
    assert outcome.review.approved
    assert outcome.route == "auto_suggest"
    assert outcome.similar_tickets[0].startswith("ALF-")


def test_pipeline_never_sends_personal_data_to_agents(container: Container):
    container.pipeline.run(ticket())
    events = container.audit.events("T-100")
    received = next(event for event in events if event["event"] == "ticket_received")
    assert received["payload"]["pii_masked"] == {"EMAIL": 1, "CPF": 1}
    serialized = str(events)
    assert "ana@cliente.com.br" not in serialized
    assert "123.456.789-09" not in serialized


def test_pipeline_writes_full_audit_trail(container: Container):
    container.pipeline.run(ticket())
    events = [(event["actor"], event["event"]) for event in container.audit.events("T-100")]
    assert events[0] == ("pipeline", "ticket_received")
    assert ("triage_agent", "completed") in events
    assert ("diagnosis_agent", "tool_call") in events
    assert ("reviewer_agent", "completed") in events
    assert events[-1] == ("pipeline", "decision")


def test_pipeline_tracks_usage_per_tenant(container: Container):
    container.pipeline.run(ticket())
    container.pipeline.run(ticket(id="T-101"))
    report = container.audit.usage_report("cliente-alfa")
    assert report["tickets"] == 2
    assert report["prompt_tokens"] > 0
    assert {row["agent"] for row in report["by_agent"]} == {
        "triage_agent",
        "diagnosis_agent",
        "reviewer_agent",
    }
    assert container.audit.usage_report("cliente-beta")["tickets"] == 0


def test_critical_ticket_requires_human_review(container: Container):
    outcome = container.pipeline.run(
        ticket(
            id="T-102",
            title="Produção parada",
            description="Produção parada: nenhum pedido entra, todos os IDocs ORDERS em status 51.",
        )
    )
    assert outcome.triage.priority.value == "P1"
    assert outcome.route == "human_review"


def test_unknown_problem_is_escalated(container: Container):
    outcome = container.pipeline.run(
        ticket(id="T-103", title="Tela azul", description="Monitor do notebook piscando e reiniciando sozinho.")
    )
    assert outcome.route == "human_review"


def test_documentation_agent_drafts_article(container: Container):
    article = container.pipeline.draft_article(
        ticket(id="T-104"),
        "Ampliado material na MM02 para o centro 1100; reprocessado IDoc na BD87",
        root_cause="Material não ampliado para o centro",
        transactions=["MM02", "BD87"],
    )
    markdown = article.to_markdown("KB-NEW")
    assert article.resolution_steps == [
        "Ampliado material na MM02 para o centro 1100",
        "reprocessado IDoc na BD87",
    ]
    assert "## Causa\nMaterial não ampliado para o centro" in markdown
    assert "ana@cliente.com.br" not in markdown


def test_evaluation_meets_quality_gates(container: Container):
    report = evaluate(container.pipeline, load_cases(ROOT / "evals" / "dataset.jsonl"))
    assert report.cases == 20
    assert report.gates(min_module_accuracy=0.85, min_retrieval_hit_rate=0.9) == []
    assert report.citation_precision >= 0.9


def test_api_endpoints(container: Container):
    client = TestClient(create_app(container))
    assert client.get("/health").json()["status"] == "ok"

    response = client.post(
        "/v1/tickets/triage",
        json={
            "id": "API-1",
            "tenant": "cliente-beta",
            "title": "Faturamento bloqueado",
            "description": "Remessa bloqueada por limite de crédito na VF01",
        },
    )
    assert response.status_code == 200
    assert response.json()["triage"]["module"] == "SD"

    assert client.get("/v1/tickets/API-1/audit").status_code == 200
    assert client.get("/v1/tickets/NAO-EXISTE/audit").status_code == 404
    assert client.get("/v1/tenants/cliente-beta/usage").json()["tickets"] == 1
    assert client.get("/v1/tenants/cliente-beta/recurrence").json()
    hits = client.post("/v1/kb/search", json={"query": "spool com erro na SP01"}).json()
    assert hits[0]["doc_id"] == "KB-010"


def test_api_returns_429_when_budget_is_exhausted(container: Container):
    container.settings.daily_token_budget_per_tenant = 10
    container.audit.record_usage("cliente-beta", "OLD", "triage_agent", "gpt-4o-mini", 50, 5, 0.0)
    client = TestClient(create_app(container))
    response = client.post(
        "/v1/tickets/triage",
        json={"tenant": "cliente-beta", "title": "Teste", "description": "Qualquer coisa"},
    )
    assert response.status_code == 429
