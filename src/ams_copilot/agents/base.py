import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ams_copilot.audit import AuditStore
from ams_copilot.llm.base import Completion, LLMClient, Message
from ams_copilot.models import UsageSummary
from ams_copilot.pricing import cost_usd
from ams_copilot.tools import ToolRegistry

OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentError(RuntimeError):
    pass


@dataclass
class RunRecorder:
    audit: AuditStore
    tenant: str
    ticket_id: str
    price_table: dict[str, tuple[float, float]]
    usage: UsageSummary = field(default_factory=UsageSummary)

    def record_completion(self, agent: str, completion: Completion) -> None:
        cost = cost_usd(
            self.price_table,
            completion.model,
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
        )
        self.usage.prompt_tokens += completion.usage.prompt_tokens
        self.usage.completion_tokens += completion.usage.completion_tokens
        self.usage.cost_usd = round(self.usage.cost_usd + cost, 6)
        self.audit.record_usage(
            self.tenant,
            self.ticket_id,
            agent,
            completion.model,
            completion.usage.prompt_tokens,
            completion.usage.completion_tokens,
            cost,
        )

    def event(self, actor: str, event: str, payload: dict[str, Any]) -> None:
        self.audit.record_event(self.tenant, self.ticket_id, actor, event, payload)


def extract_json(content: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else content
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("resposta sem objeto JSON")
    return json.loads(candidate[start : end + 1])


class Agent(Generic[OutputT]):
    name: ClassVar[str]
    task: ClassVar[str]
    instructions: ClassVar[str]
    output_model: type[OutputT]

    def __init__(
        self,
        llm: LLMClient,
        recorder: RunRecorder,
        tools: ToolRegistry | None = None,
        max_steps: int = 4,
    ) -> None:
        self.llm = llm
        self.recorder = recorder
        self.tools = tools
        self.max_steps = max_steps

    def system_prompt(self) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), ensure_ascii=False)
        return (
            f"{self.instructions}\n\n"
            "Responda somente com um objeto JSON válido que siga este schema, sem texto fora do JSON:\n"
            f"{schema}"
        )

    def run(self, payload: dict[str, Any]) -> OutputT:
        messages = [
            Message(role="system", content=self.system_prompt()),
            Message(role="user", content=json.dumps(payload, ensure_ascii=False, default=str)),
        ]
        started = time.perf_counter()
        for step in range(1, self.max_steps + 1):
            last_step = step == self.max_steps
            specs = None if last_step or self.tools is None else self.tools.specs()
            completion = self.llm.complete(self.task, messages, specs, json_output=specs is None)
            self.recorder.record_completion(self.name, completion)
            message = completion.message

            if message.tool_calls and self.tools is not None and not last_step:
                messages.append(message)
                for call in message.tool_calls:
                    result, ok = self.tools.execute(call)
                    self.recorder.event(
                        self.name,
                        "tool_call",
                        {"tool": call.name, "arguments": call.arguments, "ok": ok, "step": step},
                    )
                    messages.append(Message(role="tool", content=result, tool_call_id=call.id, name=call.name))
                continue

            try:
                output = self.output_model.model_validate(extract_json(message.content))
            except (ValueError, ValidationError) as error:
                self.recorder.event(self.name, "invalid_output", {"step": step, "error": str(error)[:500]})
                messages.append(message)
                messages.append(
                    Message(
                        role="user",
                        content=f"A resposta anterior não seguiu o schema: {str(error)[:300]}. Responda de novo só com o JSON.",
                    )
                )
                continue

            self.recorder.event(
                self.name,
                "completed",
                {
                    "step": step,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "output": output.model_dump(mode="json"),
                },
            )
            return output

        self.recorder.event(self.name, "failed", {"reason": "limite de passos atingido"})
        raise AgentError(f"{self.name} não concluiu em {self.max_steps} passos")
