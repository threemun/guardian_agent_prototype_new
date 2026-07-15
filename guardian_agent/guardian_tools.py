from __future__ import annotations

import json
import uuid
from typing import Any

from agent.conversation import handle_night_turn
from agent.contracts import ElderIntent
from agent.db import dumps, get_conn, init_db, now_iso, row_to_dict
from agent.health import HealthAgent
from agent.night import NightCareAgent
from agent.seed import seed_demo_data
from agent.message import process_guardian_message
from agent.voice import voice_alert_command
from simulator.scenarios import scenario_payload


VALID_FEEDBACK_TYPES = {intent.value for intent in ElderIntent}
VALID_NIGHT_WORKFLOW_ACTIONS = {
    "list_elders",
    "get_active_event",
    "get_event_detail",
    "get_event_timeline",
    "submit_feedback",
    "handle_elder_reply",
    "night_turn",
    "request_emergency_help",
    "confirm_return_to_bed",
    "no_response_timeout",
    "record_device_action",
    "close_event",
    "ingest_guardian_event",
    "simulate_guardian_scenario",
}
VALID_HEALTH_WORKFLOW_ACTIONS = {
    "daily_report",
    "weekly_report",
    "get_daily_report",
    "generate_daily_report",
    "get_weekly_report",
    "generate_weekly_report",
    "get_recent_vitals",
    "refresh_all_reports",
}
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
    confidence: float | str | None = None,
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
        normalized_confidence = _normalize_optional_confidence(confidence)
        normalized_source = source.strip() or "tuya_agent"
        updated = agent.apply_feedback(
            event_id,
            feedback_type,
            original_text=original_text.strip(),
            source=normalized_source,
            confidence=normalized_confidence,
        )
        agent_result = _build_agent_result(
            updated,
            requested_feedback_type=feedback_type,
            confidence=normalized_confidence,
        )
        _record_agent_turn(
            conn,
            event=updated,
            original_text=original_text.strip(),
            source=normalized_source,
            agent_result=agent_result,
        )
        return {
            "accepted": True,
            "event": updated,
            "voice_alert": voice_alert_command(updated),
            "reply_text": agent_result["reply_text"],
            "agent_result": agent_result,
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
        updated = agent.close_event(event_id, source="tuya_agent", confirmed_by_human=False)
        return {
            "closed": True,
            "event": updated,
            "voice_alert": voice_alert_command(updated),
            "message": "事件已关闭并归档。",
        }


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
    confidence: float | str | None = None,
    timeout_attempts: int = 1,
    scenario_code: str = "",
    guardian_message_json: str = "",
) -> dict[str, Any]:
    """
    One Tuya-facing workflow tool for night-care events.

    Supported actions: list_elders, get_active_event, get_event_detail,
    get_event_timeline, submit_feedback, handle_elder_reply, night_turn,
    request_emergency_help, confirm_return_to_bed, no_response_timeout,
    record_device_action, close_event.

    handle_elder_reply resolves the elder's active event when event_id is empty,
    so conversational agents should call it directly without a prior query.
    """
    normalized_action = _normalize_action(action, VALID_NIGHT_WORKFLOW_ACTIONS, "night workflow action")

    if normalized_action == "list_elders":
        return {"workflow": "night_care", "action": normalized_action, **list_elders()}
    if normalized_action == "get_active_event":
        return {"workflow": "night_care", "action": normalized_action, **get_active_event(elder_id)}
    if normalized_action == "get_event_detail":
        _require_text(event_id, "event_id")
        return {"workflow": "night_care", "action": normalized_action, "event": get_event_detail(event_id)}
    if normalized_action == "get_event_timeline":
        _require_text(event_id, "event_id")
        return {"workflow": "night_care", "action": normalized_action, **get_event_timeline(event_id)}
    if normalized_action == "submit_feedback":
        _require_text(event_id, "event_id")
        _require_text(feedback_type, "feedback_type")
        return {
            "workflow": "night_care",
            "action": normalized_action,
            **submit_elder_feedback(
                event_id=event_id,
                elder_id=elder_id,
                feedback_type=feedback_type,
                original_text=original_text,
                source=source,
                confidence=_normalize_optional_confidence(confidence),
            ),
        }
    if normalized_action == "handle_elder_reply":
        _require_text(feedback_type, "feedback_type")
        target_event_id = event_id.strip() or _active_event_id(elder_id)
        return {
            "workflow": "night_care",
            "action": normalized_action,
            **submit_elder_feedback(
                event_id=target_event_id,
                elder_id=elder_id,
                feedback_type=feedback_type,
                original_text=original_text,
                source=source,
                confidence=_normalize_optional_confidence(confidence),
            ),
        }
    if normalized_action == "night_turn":
        _require_text(original_text, "original_text")
        with get_conn() as conn:
            return {
                "workflow": "night_care",
                "action": normalized_action,
                **handle_night_turn(
                    conn,
                    {
                        "elder_id": elder_id,
                        "event_id": event_id,
                        "text": original_text,
                        "source": source,
                    },
                ),
            }
    if normalized_action == "request_emergency_help":
        target_event_id = event_id.strip() or _active_event_id(elder_id)
        return {
            "workflow": "night_care",
            "action": normalized_action,
            **request_emergency_help(
                event_id=target_event_id,
                elder_id=elder_id,
                original_text=original_text or "老人请求帮助",
            ),
        }
    if normalized_action == "confirm_return_to_bed":
        target_event_id = event_id.strip() or _active_event_id(elder_id)
        with get_conn() as conn:
            event = NightCareAgent(conn).confirm_return_to_bed(
                target_event_id,
                source=source,
                detail=original_text or "涂鸦或设备确认老人已返床。",
            )
            return {
                "workflow": "night_care",
                "action": normalized_action,
                "event": event,
                "message": "返床确认已写入 Guardian 事件时间线。",
            }
    if normalized_action == "no_response_timeout":
        target_event_id = event_id.strip() or _active_event_id(elder_id)
        with get_conn() as conn:
            event = NightCareAgent(conn).simulate_timeout(
                target_event_id,
                attempts=max(1, int(timeout_attempts or 1)),
                source=source,
            )
            return {
                "workflow": "night_care",
                "action": normalized_action,
                "event": event,
                "voice_alert": voice_alert_command(event),
                "message": "无响应超时已写入 Guardian 事件时间线。",
            }
    if normalized_action == "record_device_action":
        _require_text(event_id, "event_id")
        _require_text(device_action, "device_action")
        return {
            "workflow": "night_care",
            "action": normalized_action,
            **record_device_action(
                event_id=event_id,
                action=device_action,
                success=_normalize_bool(device_success),
                detail=device_detail,
                source=source,
            ),
        }
    if normalized_action == "close_event":
        target_event_id = event_id.strip() or _active_event_id(elder_id)
        return {"workflow": "night_care", "action": normalized_action, **close_event(target_event_id)}
    if normalized_action == "ingest_guardian_event":
        _require_text(guardian_message_json, "guardian_message_json")
        try:
            message = json.loads(guardian_message_json)
        except json.JSONDecodeError as exc:
            raise ValueError("guardian_message_json must be valid JSON") from exc
        if not isinstance(message, dict):
            raise ValueError("guardian_message_json must contain one JSON object")
        with get_conn() as conn:
            result = process_guardian_message(conn, message)
        event = result.get("event") or {}
        return {
            "workflow": "night_care",
            "action": normalized_action,
            **result,
            "voice_alert": voice_alert_command(event),
        }
    if normalized_action == "simulate_guardian_scenario":
        _require_text(scenario_code, "scenario_code")
        payload = scenario_payload(scenario_code.strip(), elder_id)
        with get_conn() as conn:
            results = [process_guardian_message(conn, message) for message in payload["messages"]]
        return {
            "workflow": "night_care",
            "action": normalized_action,
            "scenario_code": payload["scenario_code"],
            "expectation": payload["expectation"],
            "results": results,
            "message": "模拟场景的标准硬件消息已进入 Guardian 状态机。",
        }

    raise ValueError(f"unsupported night workflow action: {action}")


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


def health_report_workflow(
    action: str = "weekly_report",
    elder_id: str = "E001",
    report_date: str = "",
    week_end: str = "",
    limit: int = 7,
) -> dict[str, Any]:
    """
    One Tuya-facing workflow tool for daily/weekly health reports.

    Supported actions: daily_report, weekly_report, get_daily_report,
    generate_daily_report, get_weekly_report, generate_weekly_report,
    get_recent_vitals, refresh_all_reports.
    """
    normalized_action = _normalize_action(action, VALID_HEALTH_WORKFLOW_ACTIONS, "health workflow action")

    if normalized_action == "daily_report":
        report = get_daily_report(elder_id)
        if not report.get("found"):
            report = generate_daily_report(elder_id, report_date)
        return {"workflow": "health_report", "action": normalized_action, **report}
    if normalized_action == "weekly_report":
        report = get_weekly_report(elder_id)
        if not report.get("found"):
            report = generate_weekly_report(elder_id, week_end)
        return {"workflow": "health_report", "action": normalized_action, **report}
    if normalized_action == "get_daily_report":
        return {"workflow": "health_report", "action": normalized_action, **get_daily_report(elder_id)}
    if normalized_action == "generate_daily_report":
        return {"workflow": "health_report", "action": normalized_action, **generate_daily_report(elder_id, report_date)}
    if normalized_action == "get_weekly_report":
        return {"workflow": "health_report", "action": normalized_action, **get_weekly_report(elder_id)}
    if normalized_action == "generate_weekly_report":
        return {"workflow": "health_report", "action": normalized_action, **generate_weekly_report(elder_id, week_end)}
    if normalized_action == "get_recent_vitals":
        return {"workflow": "health_report", "action": normalized_action, **get_recent_vitals(elder_id, limit)}
    if normalized_action == "refresh_all_reports":
        daily = generate_daily_report(elder_id, report_date)
        weekly = generate_weekly_report(elder_id, week_end)
        vitals = get_recent_vitals(elder_id, limit)
        return {
            "workflow": "health_report",
            "action": normalized_action,
            "elder_id": elder_id,
            "daily_report": daily,
            "weekly_report": weekly,
            "recent_vitals": vitals,
            "report_note": HEALTH_REPORT_NOTE,
        }

    raise ValueError(f"unsupported health workflow action: {action}")


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


def _active_event_id(elder_id: str) -> str:
    active = get_active_event(elder_id)
    if not active.get("found"):
        raise ValueError(f"no active event found for elder_id: {elder_id}")
    return active["event"]["id"]


def _normalize_action(action: str, allowed: set[str], field_name: str) -> str:
    _require_text(action, field_name)
    normalized = action.strip()
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"invalid {field_name}; expected one of: {allowed_text}")
    return normalized


def _normalize_bool(value: bool | str | int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ok", "success", "succeeded"}
    return bool(value)


def _normalize_optional_confidence(value: float | str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be empty or a number between 0 and 1") from exc
    if not 0 <= parsed <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return parsed


def _build_agent_result(
    event: dict[str, Any],
    requested_feedback_type: str,
    confidence: float | None,
) -> dict[str, Any]:
    feedback_type = requested_feedback_type
    feedback_steps = [item for item in event.get("timeline", []) if item.get("step_type") == "feedback"]
    if feedback_steps:
        feedback_type = feedback_steps[-1].get("result", {}).get("feedback_type") or feedback_type

    status = event.get("status", "")
    if status in {"WAITING_FAMILY_CONFIRM", "ESCALATED"}:
        reply_text = "检测到您存在安全问题，我已联系您的子女。"
    elif status == "CLARIFYING":
        reply_text = "您现在有没有头晕、疼痛，或者需要我联系家人？"
    else:
        reply_text = {
            "bathroom": "好的，您慢点走，注意脚下，我会留意您是否安全返床。",
            "drink": "好的，您慢点走，注意脚下，我会留意您是否安全返床。",
            "ok": "好的，请您慢慢走，我会继续留意您的安全。",
        }.get(feedback_type, "好的，我已经记录，会继续留意您的安全。")

    return {
        "contract_version": "1.0",
        "provider": "tuya_agent",
        "elder_id": event.get("elder_id", ""),
        "event_id": event.get("id", ""),
        "intent": feedback_type,
        "feedback_type": feedback_type,
        "confidence": confidence,
        "requires_clarification": status == "CLARIFYING",
        "event_status": status,
        "risk_level": event.get("risk_level", ""),
        "reply_text": reply_text,
        "tool_calls": ["night_care_workflow.handle_elder_reply"],
        "reason": event.get("description", ""),
    }


def _record_agent_turn(
    conn,
    event: dict[str, Any],
    original_text: str,
    source: str,
    agent_result: dict[str, Any],
) -> None:
    request = {
        "elder_id": event.get("elder_id", ""),
        "event_id": event.get("id", ""),
        "text": original_text,
        "source": source,
    }
    response = {
        **agent_result,
        "agent_result": agent_result,
        "debug": {
            "engine": "tuya_agent_mcp",
            "temporary_agent_substitute": False,
        },
    }
    conn.execute(
        """
        INSERT INTO conversation_turns
        (id, event_id, elder_id, session_id, source, request_json, response_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"turn_{uuid.uuid4().hex[:12]}",
            event.get("id", ""),
            event.get("elder_id", ""),
            f"tuya-{event.get('elder_id', '')}",
            source,
            dumps(request),
            dumps(response),
            now_iso(),
        ),
    )
    conn.commit()


def _normalize_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 7
    return max(1, min(parsed, 30))
