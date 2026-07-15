from __future__ import annotations

import datetime as dt
import uuid
from typing import Any


def guardian_message(
    event_type: str,
    elder_id: str = "E001",
    device_type: str = "system",
    device_id: str = "",
    data: dict[str, Any] | None = None,
    raw_payload: dict[str, Any] | None = None,
    source_system: str = "simulator",
) -> dict[str, Any]:
    occurred_at = dt.datetime.now().replace(microsecond=0).isoformat()
    return {
        "schema_version": "1.0",
        "message_id": f"{source_system}-{elder_id}-{event_type.lower()}-{uuid.uuid4().hex[:8]}",
        "source_system": source_system,
        "device_type": device_type,
        "device_id": device_id,
        "elder_id": elder_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "received_at": occurred_at,
        "data": data or {},
        "raw_payload": raw_payload or {},
    }


def leave_bed_message(
    elder_id: str,
    scenario_code: str,
    no_body_seconds: int = 180,
    radar_movement: bool = True,
    location: str = "卧室",
) -> dict[str, Any]:
    return guardian_message(
        event_type="LEAVE_BED",
        elder_id=elder_id,
        device_type="sleep_band",
        device_id=f"SLEEP-{elder_id}",
        data={
            "no_body_seconds": no_body_seconds,
            "radar_movement": radar_movement,
            "night_time": True,
            "ambient_light": "low",
            "location": location,
        },
        raw_payload={"simulation_scenario": scenario_code},
    )


def return_to_bed_message(elder_id: str, detail: str = "睡眠带重新检测到床上有人。") -> dict[str, Any]:
    return guardian_message(
        event_type="RETURN_TO_BED",
        elder_id=elder_id,
        device_type="sleep_band",
        device_id=f"SLEEP-{elder_id}",
        data={"detail": detail},
        raw_payload={"simulation_scenario": "return_to_bed"},
    )


def no_response_timeout_message(elder_id: str) -> dict[str, Any]:
    return guardian_message(
        event_type="NO_RESPONSE_TIMEOUT",
        elder_id=elder_id,
        device_type="system",
        device_id="guardian-timer",
        data={"timeout_seconds": 60, "detail": "老人端未在设定时间内反馈。"},
        raw_payload={"simulation_scenario": "no_response"},
    )


def fall_detected_message(elder_id: str) -> dict[str, Any]:
    return guardian_message(
        event_type="FALL_DETECTED",
        elder_id=elder_id,
        device_type="radar",
        device_id=f"RADAR-{elder_id}",
        data={"fall_status": True, "location": "卧室"},
        raw_payload={"simulation_scenario": "fall_detected"},
    )
