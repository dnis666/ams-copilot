import json
from typing import Any

import httpx

from ams_copilot.llm.base import Completion, Message, ToolCall, ToolSpec, Usage


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        max_output_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)

    def complete(
        self,
        task: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_output: bool = False,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
            "messages": [self._encode(message) for message in messages],
            "user": task,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        elif json_output:
            payload["response_format"] = {"type": "json_object"}

        response = self._http.post("/chat/completions", json=payload)
        response.raise_for_status()
        body = response.json()
        raw = body["choices"][0]["message"]
        calls = [
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=json.loads(call["function"].get("arguments") or "{}"),
            )
            for call in raw.get("tool_calls") or []
        ]
        usage = body.get("usage") or {}
        return Completion(
            message=Message(role="assistant", content=raw.get("content") or "", tool_calls=calls),
            usage=Usage(
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            ),
            model=body.get("model", self.model),
        )

    def close(self) -> None:
        self._http.close()

    @staticmethod
    def _encode(message: Message) -> dict[str, Any]:
        data: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        return data
