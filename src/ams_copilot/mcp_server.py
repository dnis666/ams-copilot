from dataclasses import asdict
from functools import lru_cache
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from ams_copilot.config import get_settings
from ams_copilot.models import Ticket
from ams_copilot.pipeline import Container, build_container

server = MCPServer("ams-copilot", instructions="Ferramentas de triagem e diagnóstico de chamados de AMS SAP.")


@lru_cache
def container() -> Container:
    return build_container(get_settings())


@server.tool(description="Busca artigos da base de conhecimento de AMS SAP por similaridade semântica.")
def search_knowledge_base(query: str, module: str | None = None, top_k: int = 4) -> list[dict[str, Any]]:
    return [hit.as_dict() for hit in container().knowledge_base.search(query, top_k, module)]


@server.tool(description="Executa triagem, diagnóstico e revisão de um chamado e devolve a decisão com fontes e custo.")
def triage_ticket(tenant: str, title: str, description: str) -> dict[str, Any]:
    ticket = Ticket(id=f"MCP-{uuid4().hex[:8].upper()}", tenant=tenant, title=title, description=description)
    return container().pipeline.run(ticket).model_dump(mode="json")


@server.tool(description="Agrupa chamados recorrentes do cliente pela causa raiz dominante.")
def ticket_recurrence(tenant: str) -> list[dict[str, Any]]:
    return [asdict(cluster) for cluster in container().history.recurrence(tenant)]


@server.tool(description="Consumo de tokens e custo por agente do cliente no período.")
def tenant_usage(tenant: str, days: int = 30) -> dict[str, Any]:
    return container().audit.usage_report(tenant, days)


@server.tool(description="Trilha de auditoria completa das ações da IA em um chamado.")
def ticket_audit_trail(ticket_id: str) -> list[dict[str, Any]]:
    return container().audit.events(ticket_id)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
