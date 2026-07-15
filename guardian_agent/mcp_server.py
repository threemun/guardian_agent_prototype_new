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
        "elder feedback classified by the Tuya LLM, record device actions, and read or generate health "
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
def night_care_workflow(
    action: str,
    elder_id: str = "E001",
    event_id: str = "",
    feedback_type: str = "",
    original_text: str = "",
    source: str = "tuya_agent",
    device_action: str = "",
    device_success: bool = True,
    device_detail: str = "",
    confidence: str = "",
    timeout_attempts: int = 1,
    scenario_code: str = "",
    guardian_message_json: str = "",
) -> dict:
    """
    Run the night-care workflow through one tool.

    action options:
    list_elders, get_active_event, get_event_detail, get_event_timeline,
    submit_feedback, handle_elder_reply, request_emergency_help,
    confirm_return_to_bed, no_response_timeout, record_device_action, close_event,
    ingest_guardian_event, simulate_guardian_scenario.

    For elder speech, call handle_elder_reply directly with feedback_type,
    original_text and confidence. event_id may be empty; the server resolves
    the elder's active event. Do not call get_active_event first and do not use
    the legacy local night_turn action from a Tuya Agent.
    """
    return guardian_tools.night_care_workflow(
        action=action,
        elder_id=elder_id,
        event_id=event_id,
        feedback_type=feedback_type,
        original_text=original_text,
        source=source,
        device_action=device_action,
        device_success=device_success,
        device_detail=device_detail,
        confidence=confidence,
        timeout_attempts=timeout_attempts,
        scenario_code=scenario_code,
        guardian_message_json=guardian_message_json,
    )


@mcp.tool()
def health_report_workflow(
    action: str = "weekly_report",
    elder_id: str = "E001",
    report_date: str = "",
    week_end: str = "",
    limit: int = 7,
) -> dict:
    """
    Run daily/weekly health report workflow through one tool.

    action options:
    daily_report, weekly_report, get_daily_report, generate_daily_report,
    get_weekly_report, generate_weekly_report, get_recent_vitals,
    refresh_all_reports. Advisory only, not medical diagnosis.
    """
    return guardian_tools.health_report_workflow(
        action=action,
        elder_id=elder_id,
        report_date=report_date,
        week_end=week_end,
        limit=limit,
    )


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
