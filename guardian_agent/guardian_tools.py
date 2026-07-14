from __future__ import annotations

from typing import Any

from agent.db import get_conn, init_db, row_to_dict
from agent.health import HealthAgent
from agent.night import NightCareAgent
from agent.seed import seed_demo_data


VALID_FEEDBACK_TYPES = {"ok", "bathroom", "drink", "dizzy", "need_help"}
HEALTH_REPORT_NOTE = "本报告仅用于日常健康管理参考，不能替代医生诊断；如老人出现明显不适，请及时联系医护人员。"


def ensure_demo_database() -> None:
    """Create the database and seed demo data when the project is first run."""
    init_db(reset=False)
    with get_conn() as conn:
        elder_count = conn.execute("SELECT COUNT(*) FROM elders").fetchone()[0]
    if elder_count == 0:
        seed_demo_data(reset=True)


def list_elders() -> dict[str, Any]:
    """List demo elders so tool testing does not need hard-coded guesses."""
    ensure_demo_database()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, room, care_level, device_host FROM elders ORDER BY id"
        ).fetchall()
        return {"items": [row_to_dict(row) for row in rows]}


def get_active_event(elder_id: str = "E001") -> dict[str, Any]:
    """Return the newest non-closed care event for an elder."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM events
            WHERE elder_id = ? AND status != 'CLOSED'
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (elder_id,),
        ).fetchone()
        if not row:
            return {
                "found": False,
                "elder_id": elder_id,
                "message": "当前没有待处理的照护事件。",
            }
        event = NightCareAgent(conn).get_event(row["id"])
        return {"found": True, "event": event}


def get_event_detail(event_id: str) -> dict[str, Any]:
    """Return one event including elder information and its full timeline."""
    _require_text(event_id, "event_id")
    ensure_demo_database()
    with get_conn() as conn:
        event = NightCareAgent(conn).get_event(event_id)
        if not event:
            raise ValueError(f"event not found: {event_id}")
        return event


def get_event_timeline(event_id: str) -> dict[str, Any]:
    """Return the auditable observation, decision, tool and feedback steps."""
    event = get_event_detail(event_id)
    return {
        "event_id": event_id,
        "status": event["status"],
        "risk_level": event["risk_level"],
        "items": event["timeline"],
    }


def submit_elder_feedback(
    event_id: str,
    feedback_type: str,
    original_text: str = "",
    source: str = "tuya_agent",
    elder_id: str = "",
) -> dict[str, Any]:
    """Apply a normalized elder response to an existing Guardian event."""
    _require_text(event_id, "event_id")
    if feedback_type not in VALID_FEEDBACK_TYPES:
        allowed = ", ".join(sorted(VALID_FEEDBACK_TYPES))
        raise ValueError(f"invalid feedback_type; expected one of: {allowed}")

    ensure_demo_database()
    with get_conn() as conn:
        agent = NightCareAgent(conn)
        event = agent.get_event(event_id)
        if not event:
            raise ValueError(f"event not found: {event_id}")
        if elder_id and event["elder_id"] != elder_id:
            raise ValueError("event_id does not belong to elder_id")
        if event["status"] == "CLOSED":
            raise ValueError("event is already closed")
        updated = agent.apply_feedback(
            event_id,
            feedback_type,
            original_text=original_text.strip(),
            source=source.strip() or "tuya_agent",
        )
        return {
            "accepted": True,
            "event": updated,
            "message": "老人反馈已写入 Guardian 事件时间线。",
        }


def request_emergency_help(
    event_id: str,
    original_text: str = "老人请求帮助",
    elder_id: str = "",
) -> dict[str, Any]:
    """Escalate an active event when the elder explicitly asks for help."""
    return submit_elder_feedback(
        event_id=event_id,
        elder_id=elder_id,
        feedback_type="need_help",
        original_text=original_text,
        source="tuya_agent",
    )


def record_device_action(
    event_id: str,
    action: str,
    success: bool,
    detail: str = "",
    source: str = "tuya_agent",
) -> dict[str, Any]:
    """Record the result of a Tuya light or scene action in the timeline."""
    _require_text(event_id, "event_id")
    _require_text(action, "action")
    ensure_demo_database()
    with get_conn() as conn:
        updated = NightCareAgent(conn).record_device_action(
            event_id=event_id,
            action=action.strip(),
            success=success,
            detail=detail.strip(),
            source=source.strip() or "tuya_agent",
        )
        return {
            "recorded": True,
            "event": updated,
            "message": "设备动作结果已写入 Guardian 事件时间线。",
        }


def close_event(event_id: str) -> dict[str, Any]:
    """Close an event after a human or trusted workflow confirms resolution."""
    _require_text(event_id, "event_id")
    ensure_demo_database()
    with get_conn() as conn:
        agent = NightCareAgent(conn)
        event = agent.get_event(event_id)
        if not event:
            raise ValueError(f"event not found: {event_id}")
        if event["status"] == "CLOSED":
            return {"closed": True, "event": event, "message": "事件此前已经关闭。"}
        updated = agent.close_event(event_id)
        return {"closed": True, "event": updated, "message": "事件已关闭并归档。"}


def get_daily_report(elder_id: str = "E001") -> dict[str, Any]:
    """Return the latest stored daily health report for an elder."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        report = HealthAgent(conn).latest_report(elder_id, "daily")
        if not report:
            return {
                "found": False,
                "elder_id": elder_id,
                "report_note": HEALTH_REPORT_NOTE,
                "message": "当前没有已生成的健康日报。",
            }
        return _report_payload(report)


def generate_daily_report(elder_id: str = "E001", report_date: str = "") -> dict[str, Any]:
    """Generate and store a daily health report from the elder's recent vitals."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        report = HealthAgent(conn).generate_daily_report(elder_id, report_date.strip() or None)
        return _report_payload(report)


def get_weekly_report(elder_id: str = "E001") -> dict[str, Any]:
    """Return the latest stored weekly health report for an elder."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        report = HealthAgent(conn).latest_report(elder_id, "weekly")
        if not report:
            return {
                "found": False,
                "elder_id": elder_id,
                "report_note": HEALTH_REPORT_NOTE,
                "message": "当前没有已生成的健康周报。",
            }
        return _report_payload(report)


def generate_weekly_report(elder_id: str = "E001", week_end: str = "") -> dict[str, Any]:
    """Generate and store a weekly health report from the elder's recent vitals."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        report = HealthAgent(conn).generate_weekly_report(elder_id, week_end.strip() or None)
        return _report_payload(report)


def get_recent_vitals(elder_id: str = "E001", limit: int = 7) -> dict[str, Any]:
    """Return recent vitals used by the daily and weekly health report tools."""
    _require_text(elder_id, "elder_id")
    ensure_demo_database()
    with get_conn() as conn:
        items = HealthAgent(conn).latest_vitals(elder_id, _normalize_limit(limit))
        return {
            "elder_id": elder_id,
            "items": items,
            "count": len(items),
            "report_note": HEALTH_REPORT_NOTE,
        }


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "found": True,
        "elder_id": report["elder_id"],
        "report_type": report["report_type"],
        "period_start": report["period_start"],
        "period_end": report["period_end"],
        "risk_level": report["risk_level"],
        "title": report["title"],
        "summary": report["summary"],
        "content": report.get("content", {}),
        "created_at": report["created_at"],
        "report_note": HEALTH_REPORT_NOTE,
    }


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _normalize_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 7
    return max(1, min(parsed, 30))
