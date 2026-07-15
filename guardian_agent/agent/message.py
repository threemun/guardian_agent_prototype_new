from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any

from .contracts import CONTRACT_VERSION, GuardianEventType, enum_values
from .db import dumps, now_iso, row_to_dict
from .health import HealthAgent
from .night import NightCareAgent


SUPPORTED_EVENT_TYPES = set(enum_values(GuardianEventType))
SUPPORTED_DEVICE_TYPES = {"sleep_band", "radar", "voice_client", "simulator", "system"}
ALLOWED_FIELDS = {
    "schema_version",
    "message_id",
    "source_system",
    "device_type",
    "device_id",
    "elder_id",
    "event_type",
    "occurred_at",
    "received_at",
    "data",
    "raw_payload",
    "trace_id",
}


@dataclass(frozen=True)
class GuardianMessage:
    """Validated runtime model for the GuardianMessage 1.0 boundary."""

    schema_version: str
    message_id: str
    source_system: str
    device_type: str
    device_id: str
    elder_id: str
    event_type: str
    occurred_at: str
    received_at: str
    data: dict[str, Any]
    raw_payload: dict[str, Any]
    trace_id: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GuardianMessage":
        if not isinstance(payload, dict):
            raise ValueError("GuardianMessage must be a JSON object")

        unknown_fields = sorted(set(payload) - ALLOWED_FIELDS)
        if unknown_fields:
            raise ValueError(f"unsupported GuardianMessage fields: {', '.join(unknown_fields)}")

        schema_version = _required_text(payload, "schema_version", 16)
        if schema_version != CONTRACT_VERSION:
            raise ValueError(f"schema_version must be {CONTRACT_VERSION}")

        event_type = _required_text(payload, "event_type", 64)
        if event_type not in SUPPORTED_EVENT_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
            raise ValueError(f"unsupported event_type; expected one of: {allowed}")

        device_type = _required_text(payload, "device_type", 64)
        if device_type not in SUPPORTED_DEVICE_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_DEVICE_TYPES))
            raise ValueError(f"unsupported device_type; expected one of: {allowed}")

        data = payload.get("data")
        raw_payload = payload.get("raw_payload")
        if not isinstance(data, dict):
            raise ValueError("data must be an object")
        if not isinstance(raw_payload, dict):
            raise ValueError("raw_payload must be an object")

        occurred_at = _required_text(payload, "occurred_at", 64)
        _validate_date_time(occurred_at, "occurred_at")
        received_at = str(payload.get("received_at") or _local_now_iso())
        _validate_date_time(received_at, "received_at")

        return cls(
            schema_version=schema_version,
            message_id=_required_text(payload, "message_id", 128),
            source_system=_required_text(payload, "source_system", 64),
            device_type=device_type,
            device_id=_required_text(payload, "device_id", 128),
            elder_id=_required_text(payload, "elder_id", 64),
            event_type=event_type,
            occurred_at=occurred_at,
            received_at=received_at,
            data=data,
            raw_payload=raw_payload,
            trace_id=_optional_text(payload.get("trace_id"), "trace_id", 128),
        )

    def to_dict(self) -> dict[str, Any]:
        message = asdict(self)
        if not self.trace_id:
            message.pop("trace_id")
        return message


def normalize_guardian_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one GuardianMessage 1.0 JSON object."""

    return GuardianMessage.from_payload(payload).to_dict()


def process_guardian_message(conn, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist and dispatch one message exactly once by message_id."""

    message = normalize_guardian_message(payload)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_messages
        (message_id, source, topic, elder_id, payload_json, received_at, processed_status, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message["message_id"],
            message["source_system"],
            f"guardian.{message['event_type'].lower()}",
            message["elder_id"],
            dumps(message),
            message["received_at"],
            "accepted",
            dumps({}),
        ),
    )

    if cursor.rowcount == 0:
        existing = row_to_dict(
            conn.execute(
                "SELECT * FROM raw_messages WHERE message_id = ?",
                (message["message_id"],),
            ).fetchone()
        )
        previous_result = (existing or {}).get("result") or {}
        return {
            "accepted": True,
            "duplicate": True,
            "message": (existing or {}).get("payload") or message,
            **previous_result,
            "note": "message_id 已处理，本次返回第一次处理结果，未重复触发状态机。",
        }

    result = _dispatch_message(conn, message)
    event = result.get("event")
    if event:
        agent = NightCareAgent(conn)
        agent.record_input_message(
            event["id"],
            message,
            prepend=message["event_type"] == GuardianEventType.LEAVE_BED.value,
        )
        result["event"] = agent.get_event(event["id"])

    conn.execute(
        """
        UPDATE raw_messages
        SET processed_status = ?, result_json = ?
        WHERE message_id = ?
        """,
        ("processed", dumps(result), message["message_id"]),
    )
    conn.commit()
    return {"accepted": True, "duplicate": False, "message": message, **result}


def _dispatch_message(conn, message: dict[str, Any]) -> dict[str, Any]:
    event_type = message["event_type"]
    elder_id = message["elder_id"]
    data = message["data"]
    night_agent = NightCareAgent(conn)
    health_agent = HealthAgent(conn)

    if event_type == GuardianEventType.LEAVE_BED.value:
        event = night_agent.trigger_possible_leave_bed(
            elder_id=elder_id,
            scenario=str(data.get("scenario") or "standard"),
            signals=_leave_bed_signals(data),
            location=str(data.get("location") or "卧室"),
        )
        return {"event": event, "processed_action": "created_leave_bed_event"}

    if event_type == GuardianEventType.RETURN_TO_BED.value:
        event_id = str(data.get("event_id") or _latest_open_event_id(conn, elder_id))
        event = night_agent.confirm_return_to_bed(
            event_id,
            source=message["source_system"],
            detail=str(data.get("detail") or "标准消息确认老人已返床。"),
        )
        return {"event": event, "processed_action": "confirmed_return_to_bed"}

    if event_type == GuardianEventType.NO_RESPONSE_TIMEOUT.value:
        event_id = str(data.get("event_id") or _latest_open_event_id(conn, elder_id))
        event = night_agent.simulate_timeout(event_id)
        return {"event": event, "processed_action": "escalated_no_response_timeout"}

    if event_type == GuardianEventType.FALL_DETECTED.value or (
        event_type == GuardianEventType.PRESENCE_CHANGED.value and data.get("fall_status") is True
    ):
        event_id = _active_event_id(conn, elder_id)
        if not event_id:
            event_id = night_agent.trigger_possible_leave_bed(
                elder_id=elder_id,
                signals=_leave_bed_signals(data),
                location=str(data.get("location") or "卧室"),
            )["id"]
        event = night_agent.escalate_event(
            event_id,
            reason="雷达或模拟器检测到疑似跌倒，已升级为高风险事件。",
            source=message["source_system"],
            status="ESCALATED",
        )
        return {"event": event, "processed_action": "escalated_fall_detected"}

    if event_type == GuardianEventType.PRESENCE_CHANGED.value:
        event_id = _active_event_id(conn, elder_id)
        if event_id:
            return {
                "event": night_agent.get_event(event_id),
                "processed_action": "recorded_presence_change",
            }

    if event_type == GuardianEventType.VITALS_RECORDED.value:
        vital = health_agent.record_vitals(elder_id, data)
        report = health_agent.generate_daily_report(elder_id)
        return {"vital": vital, "daily_report": report, "processed_action": "recorded_vitals"}

    if event_type == GuardianEventType.DAILY_REPORT_REQUESTED.value:
        report = health_agent.generate_daily_report(elder_id, data.get("report_date"))
        return {"daily_report": report, "processed_action": "generated_daily_report"}

    if event_type == GuardianEventType.WEEKLY_REPORT_REQUESTED.value:
        report = health_agent.generate_weekly_report(elder_id, data.get("week_end"))
        return {"weekly_report": report, "processed_action": "generated_weekly_report"}

    return {"processed_action": "recorded_only", "note": f"{event_type} 已记录，当前阶段暂不改变事件状态。"}


def _required_text(payload: dict[str, Any], field_name: str, max_length: int) -> str:
    if field_name not in payload:
        raise ValueError(f"{field_name} is required")
    value = str(payload[field_name]).strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return value


def _optional_text(value: Any, field_name: str, max_length: int) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return text


def _validate_date_time(value: str, field_name: str) -> None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone offset")


def _local_now_iso() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _leave_bed_signals(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "sleep_band_no_body_seconds": int(data.get("no_body_seconds") or data.get("sleep_band_no_body_seconds") or 180),
        "radar_movement": bool(data.get("radar_movement", data.get("someone_exists", True))),
        "night_time": bool(data.get("night_time", True)),
        "ambient_light": data.get("ambient_light", "low"),
    }


def _active_event_id(conn, elder_id: str) -> str:
    row = conn.execute(
        """
        SELECT id FROM events
        WHERE elder_id = ? AND status != 'CLOSED'
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (elder_id,),
    ).fetchone()
    return str(row["id"]) if row else ""


def _latest_open_event_id(conn, elder_id: str) -> str:
    event_id = _active_event_id(conn, elder_id)
    if not event_id:
        raise ValueError(f"no active event found for elder_id: {elder_id}")
    return event_id

