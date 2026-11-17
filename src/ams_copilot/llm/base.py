from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class Completion:
    message: Message
    usage: Usage
    model: str


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


class LLMClient(Protocol):
    model: str

    def complete(
        self,
        task: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_output: bool = False,
    ) -> Completion: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
