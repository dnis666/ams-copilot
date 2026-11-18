import asyncio
import json

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import SecretStr, ValidationError

from ams_copilot import mcp_server
from ams_copilot.agents import AgentError, RunRecorder, TriageAgent
from ams_copilot.api import create_app
from ams_copilot.audit import AuditStore
from ams_copilot.config import Settings
from ams_copilot.guardrails import BudgetExceededError, decide_route
from ams_copilot.llm.base import ToolCall
from ams_copilot.llm.scripted import ScriptedLLM
from ams_copilot.models import Diagnosis, Review, Ticket, TriageDecision
from ams_copilot.rag.embeddings import OpenAICompatibleEmbedder
from ams_copilot.tools import ToolRegistry


def ticket():
    return Ticket(id="SAFE-1", tenant="cliente-alfa", title="IDoc status 51", description="Material sem centro")


def test_rejection_without_issues_never_automates():
    triage = TriageDecision(module="MM", priority="P3", ticket_type="incident", confidence=0.9, rationale="test")
    diagnosis = Diagnosis(probable_cause="test", resolution_steps=["test"], citations=["KB-004"], confidence=0.9)
    route, reasons = decide_route(triage, diagnosis, Review(approved=False), 0.6)
    assert route == "human_review"
    assert reasons


def test_authenticated_api_isolates_all_tenant_routes(container):
    container.settings.tenant_api_keys = {"cliente-alfa": SecretStr("a" * 32), "cliente-beta": SecretStr("b" * 32)}
    container.audit.record_event("cliente-alfa", "shared", "test", "test", {"value": "alpha"})
    container.audit.record_event("cliente-beta", "shared", "test", "test", {"value": "beta"})
    with TestClient(create_app(container)) as client:
        assert client.get("/v1/tickets/shared/audit").status_code == 401
        headers = {"Authorization": "Bearer " + "a" * 32}
        events = client.get("/v1/tickets/shared/audit", headers=headers).json()
        assert [event["tenant"] for event in events] == ["cliente-alfa"]
        for suffix in ("usage", "recurrence"):
            assert client.get(f"/v1/tenants/cliente-beta/{suffix}", headers=headers).status_code == 403
        data = {"tenant": "cliente-beta", "title": "Teste", "description": "Teste"}
        assert client.post("/v1/tickets/triage", json=data, headers=headers).status_code == 403
        assert (
            client.post(
                "/v1/kb/articles", json={"ticket": data, "resolution_notes": "Teste"}, headers=headers
            ).status_code
            == 403
        )
        assert client.post("/v1/kb/search", json={"query": "IDoc"}).status_code == 401
        assert client.get("/v1/tenants/cliente-alfa/usage?days=-1", headers=headers).status_code == 422
        assert (
            client.post(
                "/v1/tickets/triage",
                json={**data, "tenant": "cliente-alfa", "description": "x" * 20001},
                headers=headers,
            ).status_code
            == 422
        )


def test_mcp_limits_and_tenant_scope(container, monkeypatch):
    container.settings.mcp_tenant = "cliente-alfa"
    monkeypatch.setattr(mcp_server, "container", lambda: container)

    async def scenario():
        for name, arguments in [
            ("search_knowledge_base", {"query": "IDoc", "top_k": -1}),
            ("tenant_usage", {"tenant": "cliente-alfa", "days": 0}),
            ("ticket_recurrence", {"tenant": "cliente-beta"}),
        ]:
            with pytest.raises(ToolError):
                await mcp_server.server.call_tool(name, arguments)

    asyncio.run(scenario())


def test_tool_schema_rejects_invalid_arguments_and_hides_errors():
    registry = ToolRegistry()
    calls = []
    registry.register(
        "search",
        "search",
        {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        lambda query: calls.append(query),
    )
    for arguments in ({"query": []}, {"query": "ok", "tenant": "other"}, [], {}):
        _, ok = registry.execute(ToolCall("1", "search", arguments))
        assert not ok
    assert not calls

    def failing():
        raise RuntimeError("secret")

    registry.register("failure", "failure", {"type": "object"}, failing)
    result, ok = registry.execute(ToolCall("2", "failure", {}))
    assert not ok
    assert "secret" not in result


def test_reviewer_receives_evidence_and_documentation_masks_all_fields(container):
    class CapturingLLM(ScriptedLLM):
        def __init__(self):
            self.payloads = {}

        def complete(self, task, messages, tools=None, json_output=False):
            self.payloads[task] = self._payload(messages)
            return super().complete(task, messages, tools, json_output)

    llm = CapturingLLM()
    container.llm = llm
    container.pipeline.run(ticket())
    assert llm.payloads["review"]["evidence"][0]["content"]
    article = container.pipeline.draft_article(
        ticket(), "Contatar ana@example.com", root_cause="ana@example.com", transactions=["ana@example.com"]
    )
    assert "ana@example.com" not in json.dumps(llm.payloads)
    assert "ana@example.com" not in article.model_dump_json()


def test_budget_checked_between_calls_and_for_documentation(container):
    container.settings.daily_token_budget_per_tenant = 1
    with pytest.raises(BudgetExceededError):
        container.pipeline.run(ticket())
    events = container.audit.events(ticket().id)
    assert [e["actor"] for e in events if e["event"] == "completed"] == ["triage_agent"]
    with pytest.raises(BudgetExceededError):
        container.pipeline.draft_article(ticket(), "Resolvido na MM02")
    client = TestClient(create_app(container))
    response = client.post(
        "/v1/kb/articles", json={"ticket": ticket().model_dump(mode="json"), "resolution_notes": "Resolvido na MM02"}
    )
    assert response.status_code == 429


def test_provider_errors_become_safe_agent_errors(container):
    class FailingLLM:
        model = "test"

        def complete(self, *args, **kwargs):
            raise httpx.ReadTimeout("secret")

    container.llm = FailingLLM()
    rec = RunRecorder(container.audit, "tenant", "failed", {})
    with pytest.raises(AgentError, match="falha do provedor"):
        TriageAgent(container.llm, rec).run({})
    assert "secret" not in str(container.audit.events("failed"))
    client = TestClient(create_app(container))
    assert client.post("/v1/tickets/triage", json=ticket().model_dump(mode="json")).status_code == 502


@pytest.mark.parametrize(
    "rows",
    [[], [{"index": 0, "embedding": [1]}], [{"index": 1, "embedding": [1, 0]}], [{"index": 0, "embedding": [0, 0]}]],
)
def test_embeddings_validate_provider_response(rows):
    embedder = OpenAICompatibleEmbedder(
        "https://example.com/v1",
        "",
        "test",
        2,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": rows})),
    )
    with pytest.raises(ValueError):
        embedder.embed(["text"])
    embedder.close()


def test_embeddings_mask_pii_preserve_order_and_skip_empty_batch():
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        assert "ana@example.com" not in request.content.decode()
        return httpx.Response(
            200, json={"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [2, 0]}]}
        )

    embedder = OpenAICompatibleEmbedder("https://example.com/v1", "", "test", 2, transport=httpx.MockTransport(handler))
    assert embedder.embed([]).shape == (0, 2)
    assert np.array_equal(embedder.embed(["ana@example.com", "other"]), np.eye(2))
    embedder.close()


@pytest.mark.parametrize(
    "values",
    [
        {"max_agent_steps": 0},
        {"embedding_dimensions": -1},
        {"confidence_threshold": 2},
        {"tenant_api_keys": {"tenant": "short"}},
    ],
)
def test_invalid_configuration_fails_early(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_audit_tenant_filter_handles_duplicate_ticket_ids():
    audit = AuditStore(":memory:")
    for tenant in ("a", "b"):
        audit.record_event(tenant, "same", "test", "test", {})
    assert len(audit.events("same")) == 2
    assert [event["tenant"] for event in audit.events("same", "a")] == ["a"]
    audit.close()


def test_pipeline_reuses_history_lookup(container, monkeypatch):
    original = container.history.similar
    calls = []

    def similar(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(container.history, "similar", similar)
    container.pipeline.run(ticket())
    assert len(calls) == 1


def test_history_failure_does_not_abort_pipeline(container, monkeypatch):
    def failing(*args, **kwargs):
        raise httpx.ReadTimeout("secret")

    monkeypatch.setattr(container.history, "similar", failing)
    result = container.pipeline.run(ticket())
    assert result.similar_tickets == []
    assert "history_unavailable" in str(container.audit.events(ticket().id))
    assert "secret" not in str(container.audit.events(ticket().id))


def test_evaluation_penalizes_extra_and_unexpected_citations():
    from ams_copilot.evaluation import CaseResult, summarize

    cases = [
        CaseResult("1", "MM", "MM", "P1", "P3", "KB-1", ["KB-1"], ["KB-1", "KB-2"], "human_review", 0, 0, 0),
        CaseResult("2", "MM", "MM", "P3", "P3", None, [], ["KB-3"], "human_review", 0, 0, 0),
    ]
    report = summarize(cases)
    assert report.citation_precision == 0.333
    assert report.failures[0]["case_id"] == "1"


def test_agent_limits_tool_fanout_before_execution(container):
    from ams_copilot.agents import DiagnosisAgent
    from ams_copilot.llm.base import Completion, Message, Usage

    calls = []
    registry = ToolRegistry()
    registry.register("search", "search", {"type": "object"}, lambda: calls.append(True))

    class ExcessiveLLM:
        model = "test"

        def complete(self, *args, **kwargs):
            return Completion(
                Message("assistant", tool_calls=[ToolCall(str(i), "search", {}) for i in range(9)]), Usage(), self.model
            )

    recorder = RunRecorder(container.audit, "tenant", "fanout", {})
    with pytest.raises(AgentError, match="limite de ferramentas"):
        DiagnosisAgent(ExcessiveLLM(), recorder, registry).run({})
    assert not calls


def test_api_initializes_once_and_closes_owned_container(container, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from ams_copilot import api

    created = []
    closed = []

    def build(settings):
        created.append(True)
        return container

    monkeypatch.setattr(api, "build_container", build)
    monkeypatch.setattr(container, "close", lambda: closed.append(True))
    with TestClient(create_app()) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: client.get("/health"), range(8)))
        assert all(response.status_code == 200 for response in responses)
        assert created == [True]
        assert not closed
    assert closed == [True]


def test_diagnosis_provider_failure_routes_to_human(container):
    class FailingDiagnosis(ScriptedLLM):
        def complete(self, task, messages, tools=None, json_output=False):
            if task == "diagnosis":
                raise httpx.ReadTimeout("private")
            return super().complete(task, messages, tools, json_output)

    container.llm = FailingDiagnosis()
    outcome = container.pipeline.run(ticket())
    assert outcome.diagnosis is None
    assert outcome.route == "human_review"
    assert not outcome.review.approved
