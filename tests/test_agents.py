import json

import httpx
import pytest

from ams_copilot.agents import AgentError, DiagnosisAgent, RunRecorder, TriageAgent, extract_json
from ams_copilot.audit import AuditStore
from ams_copilot.config import DEFAULT_PRICES
from ams_copilot.llm.base import Completion, Message, ToolCall, Usage
from ams_copilot.llm.openai_compat import OpenAICompatibleClient
from ams_copilot.tools import ToolRegistry


class SequenceLLM:
    model = "gpt-4o-mini"

    def __init__(self, replies: list[Message]) -> None:
        self.replies = replies
        self.calls: list[list[Message]] = []

    def complete(self, task, messages, tools=None, json_output=False) -> Completion:
        self.calls.append(list(messages))
        return Completion(self.replies.pop(0), Usage(1000, 200), self.model)


def recorder(audit: AuditStore) -> RunRecorder:
    return RunRecorder(audit, "cliente-x", "T-1", DEFAULT_PRICES)


VALID_TRIAGE = {
    "module": "SD",
    "priority": "P2",
    "ticket_type": "incident",
    "confidence": 0.8,
    "rationale": "Bloqueio de crédito no faturamento",
}


def test_extract_json_accepts_fenced_output():
    assert extract_json('Segue:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_agent_retries_after_invalid_output_and_records_cost():
    audit = AuditStore(":memory:")
    llm = SequenceLLM(
        [
            Message("assistant", '{"module": "XX"}'),
            Message("assistant", json.dumps(VALID_TRIAGE)),
        ]
    )
    rec = recorder(audit)
    result = TriageAgent(llm, rec, max_steps=3).run({"ticket": {"title": "a", "description": "b"}})
    assert result.priority.value == "P2"
    events = [event["event"] for event in audit.events("T-1")]
    assert events == ["invalid_output", "completed"]
    assert rec.usage.prompt_tokens == 2000
    assert rec.usage.cost_usd == pytest.approx(2 * (1000 * 0.15 + 200 * 0.60) / 1_000_000)


def test_agent_executes_tool_calls_before_answering():
    audit = AuditStore(":memory:")
    seen = {}

    def search_knowledge_base(query: str, module: str | None = None):
        seen["query"] = query
        return {"results": [{"doc_id": "KB-006"}]}

    tools = ToolRegistry()
    tools.register("search_knowledge_base", "busca", {"type": "object"}, search_knowledge_base)
    diagnosis = {
        "probable_cause": "Limite de crédito excedido",
        "resolution_steps": ["Liberar na VKM3"],
        "sap_transactions": ["VKM3"],
        "citations": ["KB-006"],
        "confidence": 0.8,
    }
    llm = SequenceLLM(
        [
            Message("assistant", tool_calls=[ToolCall("c1", "search_knowledge_base", {"query": "crédito"})]),
            Message("assistant", json.dumps(diagnosis)),
        ]
    )
    result = DiagnosisAgent(llm, recorder(audit), tools, max_steps=3).run({"ticket": {}})
    assert seen["query"] == "crédito"
    assert result.citations == ["KB-006"]
    tool_messages = [message for message in llm.calls[1] if message.role == "tool"]
    assert json.loads(tool_messages[0].content) == {"results": [{"doc_id": "KB-006"}]}


def test_agent_reports_unknown_tool_to_the_model():
    audit = AuditStore(":memory:")
    llm = SequenceLLM(
        [
            Message("assistant", tool_calls=[ToolCall("c1", "drop_table", {})]),
            Message("assistant", json.dumps(VALID_TRIAGE)),
        ]
    )
    TriageAgent(llm, recorder(audit), ToolRegistry(), max_steps=3).run({"ticket": {}})
    tool_event = audit.events("T-1")[0]
    assert tool_event["event"] == "tool_call"
    assert tool_event["payload"]["ok"] is False


def test_agent_fails_after_max_steps():
    audit = AuditStore(":memory:")
    llm = SequenceLLM([Message("assistant", "não sei"), Message("assistant", "ainda não sei")])
    with pytest.raises(AgentError):
        TriageAgent(llm, recorder(audit), max_steps=2).run({"ticket": {}})
    assert audit.events("T-1")[-1]["event"] == "failed"


def test_openai_compatible_client_parses_tool_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "search_knowledge_base"
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_knowledge_base",
                                        "arguments": '{"query": "idoc"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 15},
            },
        )

    tools = ToolRegistry()
    tools.register("search_knowledge_base", "busca", {"type": "object"}, lambda query: {})
    client = OpenAICompatibleClient(
        "https://llm.local/v1", "key", "gpt-4o-mini", transport=httpx.MockTransport(handler)
    )
    completion = client.complete("diagnosis", [Message("user", "oi")], tools.specs())
    assert completion.message.tool_calls[0].arguments == {"query": "idoc"}
    assert completion.usage.prompt_tokens == 120
    assert completion.model == "gpt-4o-mini-2024-07-18"
