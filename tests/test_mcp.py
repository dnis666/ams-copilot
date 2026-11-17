import asyncio

from ams_copilot import mcp_server
from ams_copilot.pipeline import Container


def test_mcp_server_exposes_tools(container: Container, monkeypatch):
    monkeypatch.setattr(mcp_server, "container", lambda: container)

    async def scenario():
        tools = {tool.name for tool in await mcp_server.server.list_tools()}
        result = await mcp_server.server.call_tool(
            "triage_ticket",
            {"tenant": "cliente-beta", "title": "Job cancelado", "description": "Job noturno cancelado na SM37"},
        )
        return tools, str(result)

    tools, result = asyncio.run(scenario())
    assert tools == {
        "search_knowledge_base",
        "triage_ticket",
        "ticket_recurrence",
        "tenant_usage",
        "ticket_audit_trail",
    }
    assert "KB-002" in result
