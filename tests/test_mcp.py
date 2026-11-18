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


def test_mcp_stdio_protocol(tmp_path):
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "ams_copilot.mcp_server"],
            env={
                **os.environ,
                "AMS_LLM_PROVIDER": "scripted",
                "AMS_EMBEDDING_PROVIDER": "hashing",
                "AMS_DATABASE_URL": "",
                "AMS_AUDIT_DB_PATH": str(tmp_path / "mcp.db"),
            },
        )
        async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
            await session.initialize()
            listed = await session.list_tools()
            assert len(listed.tools) == 5
            result = await session.call_tool("search_knowledge_base", {"query": "IDoc status 51", "top_k": 1})
            assert not result.is_error
            assert "KB-001" in str(result)
            invalid = await session.call_tool("search_knowledge_base", {"query": "IDoc", "top_k": 0})
            assert invalid.is_error

    asyncio.run(scenario())
