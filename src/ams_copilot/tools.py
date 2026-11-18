import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from ams_copilot.llm.base import ToolCall, ToolSpec


@dataclass
class Tool:
    spec: ToolSpec
    handler: Callable[..., Any]
    validator: Draft202012Validator


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, name: str, description: str, parameters: dict[str, Any], handler: Callable[..., Any]) -> None:
        self.tools[name] = Tool(ToolSpec(name, description, parameters), handler, Draft202012Validator(parameters))

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self.tools.values()]

    def execute(self, call: ToolCall) -> tuple[str, bool]:
        tool = self.tools.get(call.name)
        if tool is None:
            return json.dumps({"error": f"ferramenta desconhecida: {call.name}"}, ensure_ascii=False), False
        if not isinstance(call.arguments, dict) or not tool.validator.is_valid(call.arguments):
            return json.dumps({"error": "argumentos inválidos"}), False
        try:
            result = tool.handler(**call.arguments)
        except Exception:
            return json.dumps({"error": "falha ao executar ferramenta"}), False
        return json.dumps(result, ensure_ascii=False, default=str), True
