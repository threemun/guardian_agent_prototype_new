from __future__ import annotations

import uuid
from typing import Any

from .db import dumps, now_iso, row_to_dict
from .health import HealthAgent
from .night import NightCareAgent


SUPPORTED_EVENT_TYPES = {
    "LEAVE_BED",
    "RETURN_TO_BED",
    "PRESENCE_CHANGED",
    "FALL_DETECTED",
    "NO_RESPONSE_TIMEOUT",
    "VOICE_TRANSCRIPT",
    "VITALS_RECORDED",
    "DAILY_REPORT_REQUESTED",
    "WEEKLY_REPORT_REQUESTED",
    "SOS_BUTTON",
}


def normalize_guardian_message(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("GuardianMessage must be a JSON object")

    event_type = str(payload.get("event_type") or "").strip().upper()
    if not event_type:
        raise ValueError("event_type is required")
    if event_type not in SUPPORTED_EVENT_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
        raise ValueError(f"unsupported event_type; expected one of: {allowed}")

    elder_id = str(payload.get("elder_id") or "").strip()
    if not elder_id:
        raise ValueError("elder_id is required")

    data = payload.get("data") or {}
    raw_payload = payload.get("raw_payload") or {}
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    if not isinstance(raw_payload, dict):
        raise ValueError("raw_payload must be an object")

    occurred_at = payload.get("occurred_at") or payload.get("timestamp") or now_iso()
    received_at = payload.get("received_at") or now_iso()
    return {
        "schema_version": str(payload.get("schema_version") or "1.0"),
        "message_id": str(payload.get("message_id") or f"guardian-{uuid.uuid4().hex}"),
        "source_system": str(payload.get("source_system") or "simulator"),
        "device_type": str(payload.get("device_type") or "system"),
        "device_id": str(payload.get("device_id") or ""),
        "elder_id": elder_id,
        "event_type": event_type,
        "occurred_at": str(occurred_at),
        "received_at": str(received_at),
        "data": data,
        "raw_payload": raw_payload,
    }


def process_guardian_message(conn, payload: dict[str, Any]) -> dict[str, Any]:
    message = normalize_guardian_message(payload)
    existing = conn.execute(
        "SELECT * FROM raw_messages WHERE message_id = ?",
        (message["message_id"],),
    ).fetchone()
    if existing:
        return {
            "accepted": True,
            "duplicate": True,
            "message": row_to_dict(existing),
            "note": "message_id 已处理，本次未重复触发状态机。",
        }

    conn.execute(
        """
        INSERT INTO raw_messages
        (message_id, source, topic, elder_id, payload_json, received_at, processed_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message["message_id"],
            message["source_system"],
            f"guardian.{message['event_type'].lower()}",
            message["elder_id"],
            dumps(message),
            message["received_at"],
            "accepted",
        ),
    )
    result = _dispatch_message(conn, message)
    conn.commit()
    return {"accepted": True, "duplicate": False, "message": message, **result}


def _dispatch_message(conn, message: dict[str, Any]) -> dict[str, Any]:
    event_type = message["event_type"]
    elder_id = message["elder_id"]
    data = message["data"]
    raw_payload = message["raw_payload"]
    night_agent = NightCareAgent(conn)
    health_agent = HealthAgent(conn)

    if event_type == "LEAVE_BED":
        event = night_agent.trigger_possible_leave_bed(
            elder_id=elder_id,
            scenario=str(raw_payload.get("simulation_scenario") or data.get("scenario") or "standard"),
            signals=_leave_bed_signals(data),
            location=str(data.get("location") or "卧室"),
        )
        return {"event": event, "processed_action": "created_leave_bed_event"}

    if event_type == "RETURN_TO_BED":
        event_id = str(data.get("event_id") or _latest_open_event_id(conn, elder_id))
        event = night_agent.confirm_return_to_bed(
            event_id,
            source=message["source_system"],
            detail=str(data.get("detail") or "标准消息确认老人已返床。"),
        )
        return {"event": event, "processed_action": "confirmed_return_to_bed"}

    if event_type == "NO_RESPONSE_TIMEOUT":
        event_id = str(data.get("event_id") or _latest_open_event_id(conn, elder_id))
        event = night_agent.simulate_timeout(event_id)
        return {"event": event, "processed_action": "escalated_no_response_timeout"}

    if event_type == "FALL_DETECTED" or (event_type == "PRESENCE_CHANGED" and data.get("fall_status") is True):
        event_id = str(data.get("event_id") or _latest_open_event_id(conn, elder_id))
        event = night_agent.escalate_event(
            event_id,
            reason="雷达或模拟器检测到疑似跌倒，已升级为高风险事件。",
            source=message["source_system"],
            status="ESCALATED",
        )
        return {"event": event, "processed_action": "escalated_fall_detected"}

    if event_type == "SOS_BUTTON":
        event = night_agent.trigger_sos(elder_id=elder_id, location=str(data.get("location") or "客厅"))
        return {"event": event, "processed_action": "created_sos_event"}

    if event_type == "VITALS_RECORDED":
        vital = health_agent.record_vitals(elder_id, data)
        report = health_agent.generate_daily_report(elder_id)
        return {"vital": vital, "daily_report": report, "processed_action": "recorded_vitals"}

    if event_type == "DAILY_REPORT_REQUESTED":
        report = health_agent.generate_daily_report(elder_id, data.get("report_date"))
        return {"daily_report": report, "processed_action": "generated_daily_report"}

    if event_type == "WEEKLY_REPORT_REQUESTED":
        report = health_agent.generate_weekly_report(elder_id, data.get("week_end"))
        return {"weekly_report": report, "processed_action": "generated_weekly_report"}

    return {"processed_action": "recorded_only", "note": f"{event_type} 已记录，当前阶段暂不改变事件状态。"}


def _leave_bed_signals(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "sleep_band_no_body_seconds": int(data.get("no_body_seconds") or data.get("sleep_band_no_body_seconds") or 180),
        "radar_movement": bool(data.get("radar_movement", data.get("someone_exists", True))),
        "night_time": bool(data.get("night_time", True)),
        "ambient_light": data.get("ambient_light", "low"),
    }


def _latest_open_event_id(conn, elder_id: str) -> str:
    row = conn.execute(
        """
        SELECT id FROM events
        WHERE elder_id = ? AND status != 'CLOSED'
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (elder_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"no active event found for elder_id: {elder_id}")
    return row["id"]
