from __future__ import annotations

import contextlib
import hmac
import os
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

import guardian_tools


HOST = os.getenv("GUARDIAN_MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("GUARDIAN_MCP_PORT", "8000"))
API_KEY = os.getenv("GUARDIAN_MCP_API_KEY", "").strip()


mcp = FastMCP(
    "Guardian Care MCP",
    instructions=(
        "Use these tools to query Guardian elder-care events, submit normalized "
        "elder feedback, record Tuya device actions, and read or generate health "
        "daily/weekly reports. Never invent an event_id. Health reports are only "
        "for daily care reference and must not be treated as a medical diagnosis."
    ),
    host=HOST,
    port=PORT,
    stateless_http=True,
    json_response=True,
    # The service listens locally by default. When exposed through a tunnel, the
    # public Host is dynamic, so DNS rebinding protection is disabled here.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class ApiKeyAuthMiddleware:
    """Accept a Bearer header or Tuya-compatible ``?key=`` authentication."""

    def __init__(self, app: Callable[..., Awaitable[None]], api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or not self.api_key:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        expected = f"Bearer {self.api_key}"
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        query_keys = parse_qs(query_string, keep_blank_values=True).get("key", [])
        query_key_matches = any(
            hmac.compare_digest(candidate, self.api_key) for candidate in query_keys
        )
        if hmac.compare_digest(supplied, expected) or query_key_matches:
            await self.app(scope, receive, send)
            return

        body = b'{"error":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


@mcp.tool()
def list_elders() -> dict:
    """List elders available to the Guardian demo and their elder IDs."""
    return guardian_tools.list_elders()


@mcp.tool()
def get_active_event(elder_id: str = "E001") -> dict:
    """Get the newest non-closed Guardian care event for an elder."""
    return guardian_tools.get_active_event(elder_id)


@mcp.tool()
def get_event_detail(event_id: str) -> dict:
    """Get one Guardian event with its current risk, status and full timeline."""
    return guardian_tools.get_event_detail(event_id)


@mcp.tool()
def get_event_timeline(event_id: str) -> dict:
    """Get the auditable decision timeline for a Guardian event."""
    return guardian_tools.get_event_timeline(event_id)


@mcp.tool()
def submit_elder_feedback(
    event_id: str,
    feedback_type: str,
    original_text: str = "",
    source: str = "tuya_agent",
    elder_id: str = "",
) -> dict:
    """
    Submit an elder response to an existing event.

    feedback_type must be one of: ok, bathroom, drink, dizzy, need_help.
    Use original_text to preserve what the elder actually said.
    """
    return guardian_tools.submit_elder_feedback(
        event_id=event_id,
        feedback_type=feedback_type,
        original_text=original_text,
        source=source,
        elder_id=elder_id,
    )


@mcp.tool()
def request_emergency_help(
    event_id: str,
    original_text: str = "老人请求帮助",
    elder_id: str = "",
) -> dict:
    """Escalate an event after the elder explicitly asks for immediate help."""
    return guardian_tools.request_emergency_help(event_id, original_text, elder_id)


@mcp.tool()
def record_device_action(
    event_id: str,
    action: str,
    success: bool,
    detail: str = "",
    source: str = "tuya_agent",
) -> dict:
    """Record a Tuya scene or device action result in the Guardian timeline."""
    return guardian_tools.record_device_action(
        event_id=event_id,
        action=action,
        success=success,
        detail=detail,
        source=source,
    )


@mcp.tool()
def close_event(event_id: str) -> dict:
    """Close and archive an event only after the situation is confirmed resolved."""
    return guardian_tools.close_event(event_id)


@mcp.tool()
def get_daily_report(elder_id: str = "E001") -> dict:
    """Get the latest stored daily health report for an elder."""
    return guardian_tools.get_daily_report(elder_id)


@mcp.tool()
def generate_daily_report(elder_id: str = "E001", report_date: str = "") -> dict:
    """Generate a daily health report from current vitals. Advisory only."""
    return guardian_tools.generate_daily_report(elder_id, report_date)


@mcp.tool()
def get_weekly_report(elder_id: str = "E001") -> dict:
    """Get the latest stored weekly health report for an elder."""
    return guardian_tools.get_weekly_report(elder_id)


@mcp.tool()
def generate_weekly_report(elder_id: str = "E001", week_end: str = "") -> dict:
    """Generate a weekly health report from current vitals. Advisory only."""
    return guardian_tools.generate_weekly_report(elder_id, week_end)


@mcp.tool()
def get_recent_vitals(elder_id: str = "E001", limit: int = 7) -> dict:
    """Get recent vitals used by the daily and weekly health report tools."""
    return guardian_tools.get_recent_vitals(elder_id, limit)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    """Start and stop the MCP Streamable HTTP session manager cleanly."""
    async with mcp.session_manager.run():
        yield


app = ApiKeyAuthMiddleware(
    Starlette(
        routes=[Mount("/", app=mcp.streamable_http_app())],
        lifespan=lifespan,
    ),
    API_KEY,
)


if __name__ == "__main__":
    guardian_tools.ensure_demo_database()
    if not API_KEY:
        print("警告：未设置 GUARDIAN_MCP_API_KEY，仅适合本机测试。")
    # Tuya only permits URL-based authentication in some Streamable HTTP configs.
    # Keep query-string credentials out of the service journal.
    uvicorn.run(app, host=HOST, port=PORT, access_log=False)
