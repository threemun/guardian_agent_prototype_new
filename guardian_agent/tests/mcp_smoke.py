from __future__ import annotations

import asyncio
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


MCP_URL = os.getenv("GUARDIAN_MCP_TEST_URL", "http://127.0.0.1:8000/mcp")
API_KEY = os.getenv("GUARDIAN_MCP_API_KEY", "").strip()
AUTH_MODE = os.getenv("GUARDIAN_MCP_AUTH_MODE", "header").strip().lower()
EXPECTED_TOOLS = {
    "list_elders",
    "night_care_workflow",
    "health_report_workflow",
}


async def smoke_test() -> None:
    """Verify the same initialize/list/call sequence a remote MCP client uses."""
    mcp_url = MCP_URL
    headers = {}
    if API_KEY and AUTH_MODE == "query":
        parts = urlsplit(mcp_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.append(("key", API_KEY))
        mcp_url = urlunsplit(parts._replace(query=urlencode(query)))
    elif API_KEY:
        headers = {"Authorization": f"Bearer {API_KEY}"}

    async with httpx.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                missing = EXPECTED_TOOLS - tool_names
                if missing:
                    raise AssertionError(f"missing MCP tools: {sorted(missing)}")

                result = await session.call_tool(
                    "night_care_workflow",
                    arguments={"action": "get_active_event", "elder_id": "E001", "confidence": ""},
                )
                if result.isError:
                    raise AssertionError(f"night_care_workflow failed: {result.content}")

                report_result = await session.call_tool(
                    "health_report_workflow",
                    arguments={"action": "weekly_report", "elder_id": "E001"},
                )
                if report_result.isError:
                    raise AssertionError(f"health_report_workflow failed: {report_result.content}")

                print("MCP initialization: OK")
                print(f"Discovered tools: {', '.join(sorted(tool_names))}")
                print("night_care_workflow: OK")
                print("health_report_workflow: OK")


if __name__ == "__main__":
    asyncio.run(smoke_test())
