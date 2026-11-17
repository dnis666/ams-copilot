import json
from typing import Any

from ams_copilot.llm.base import Completion, Message, ToolCall, ToolSpec, Usage, estimate_tokens
from ams_copilot.llm.heuristics import (
    classify_module,
    classify_priority,
    classify_type,
    extract_list,
    extract_section,
)


class ScriptedLLM:
    model = "scripted"

    def complete(
        self,
        task: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        json_output: bool = False,
    ) -> Completion:
        payload = self._payload(messages)
        handler = getattr(self, f"_{task}", None)
        if handler is None:
            raise ValueError(f"tarefa não suportada pelo modo offline: {task}")
        result = handler(payload, messages, tools or [])
        prompt_tokens = sum(estimate_tokens(message.content) for message in messages)
        if isinstance(result, list):
            message = Message(role="assistant", tool_calls=result)
            completion_tokens = estimate_tokens(json.dumps([call.arguments for call in result]))
        else:
            content = json.dumps(result, ensure_ascii=False)
            message = Message(role="assistant", content=content)
            completion_tokens = estimate_tokens(content)
        return Completion(message=message, usage=Usage(prompt_tokens, completion_tokens), model=self.model)

    @staticmethod
    def _payload(messages: list[Message]) -> dict[str, Any]:
        for message in messages:
            if message.role == "user":
                return json.loads(message.content)
        return {}

    def _triage(self, payload: dict[str, Any], *_: Any) -> dict[str, Any]:
        ticket = payload["ticket"]
        text = f"{ticket['title']}\n{ticket['description']}"
        module, confidence, scores = classify_module(text)
        hits = {name: score for name, score in scores.items() if score}
        return {
            "module": module,
            "priority": classify_priority(text),
            "ticket_type": classify_type(text),
            "confidence": confidence,
            "rationale": f"Palavras-chave por módulo: {hits or 'nenhuma'}",
        }

    def _diagnosis(
        self, payload: dict[str, Any], messages: list[Message], tools: list[ToolSpec]
    ) -> dict[str, Any] | list[ToolCall]:
        ticket = payload["ticket"]
        query = f"{ticket['title']} {ticket['description']}"
        tool_results = {message.name: json.loads(message.content) for message in messages if message.role == "tool"}
        available = {tool.name for tool in tools}
        if not tool_results and "search_knowledge_base" in available:
            calls = [
                ToolCall(
                    id="call_kb",
                    name="search_knowledge_base",
                    arguments={"query": query, "module": payload["triage"]["module"]},
                )
            ]
            if "find_similar_tickets" in available:
                calls.append(ToolCall(id="call_hist", name="find_similar_tickets", arguments={"query": query}))
            return calls

        documents = tool_results.get("search_knowledge_base", {}).get("results", [])
        similar = tool_results.get("find_similar_tickets", {}).get("results", [])
        if not documents:
            return {
                "probable_cause": "Sem artigo correspondente na base de conhecimento.",
                "resolution_steps": ["Encaminhar ao analista do módulo para investigação manual."],
                "sap_transactions": [],
                "citations": [],
                "confidence": 0.2,
            }

        top = documents[0]
        cause = extract_section(top["content"], "Causa") or top["title"]
        steps = extract_list(extract_section(top["content"], "Resolução")) or [
            "Seguir o procedimento do artigo citado."
        ]
        if similar:
            steps.append(f"Comparar com o chamado {similar[0]['ticket_id']}: {similar[0]['resolution']}")
        confidence = min(0.95, 0.35 + float(top["score"]))
        return {
            "probable_cause": cause.split("\n")[0],
            "resolution_steps": steps,
            "sap_transactions": top.get("transactions", []),
            "citations": [top["doc_id"]],
            "confidence": round(confidence, 2),
        }

    def _review(self, payload: dict[str, Any], *_: Any) -> dict[str, Any]:
        diagnosis = payload.get("diagnosis")
        sources = set(payload.get("sources", []))
        issues = []
        if not diagnosis:
            issues.append("Diagnóstico ausente.")
        else:
            if not diagnosis["citations"]:
                issues.append("Diagnóstico sem fonte na base de conhecimento.")
            ungrounded = [doc for doc in diagnosis["citations"] if doc not in sources]
            if ungrounded:
                issues.append(f"Fontes não recuperadas na busca: {ungrounded}")
            if diagnosis["confidence"] < 0.5:
                issues.append("Confiança do diagnóstico abaixo de 0.5.")
        return {"approved": not issues, "issues": issues}

    def _kb_article(self, payload: dict[str, Any], *_: Any) -> dict[str, Any]:
        ticket = payload["ticket"]
        notes = payload["resolution_notes"]
        steps = [step.strip() for step in notes.replace(";", "\n").splitlines() if step.strip()]
        module, _, _ = classify_module(f"{ticket['title']} {ticket['description']} {notes}")
        return {
            "title": ticket["title"],
            "module": payload.get("module") or module,
            "symptoms": [ticket["description"]],
            "cause": payload.get("root_cause") or "Causa a confirmar pelo analista responsável.",
            "resolution_steps": steps or [notes],
            "transactions": payload.get("transactions", []),
        }
