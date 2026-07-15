from __future__ import annotations

from typing import Any

from .event_factory import (
    fall_detected_message,
    leave_bed_message,
    no_response_timeout_message,
    return_to_bed_message,
)


SCENARIO_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "normal_bathroom": {
        "label": "正常上厕所",
        "elder_reply": "我去趟卫生间，不用担心。",
        "feedback_type": "bathroom",
        "expected_status_after_reply": "MONITORING_RETURN",
    },
    "normal_drink": {
        "label": "起床喝水",
        "elder_reply": "我起来喝口水。",
        "feedback_type": "drink",
        "expected_status_after_reply": "MONITORING_RETURN",
    },
    "dizzy": {
        "label": "老人头晕",
        "elder_reply": "我有点头晕。",
        "feedback_type": "dizzy",
        "expected_status_after_reply": "WAITING_FAMILY_CONFIRM",
    },
    "need_help": {
        "label": "老人求助",
        "elder_reply": "腿没劲，扶我一下。",
        "feedback_type": "need_help",
        "expected_status_after_reply": "WAITING_FAMILY_CONFIRM",
    },
    "no_response": {
        "label": "没有回答",
        "elder_reply": "",
        "feedback_type": "",
        "expected_status_after_messages": "WAITING_FAMILY_CONFIRM",
    },
    "fall_detected": {
        "label": "疑似跌倒",
        "elder_reply": "",
        "feedback_type": "",
        "expected_status_after_messages": "ESCALATED",
    },
    "return_to_bed": {
        "label": "已返床",
        "elder_reply": "我回床了。",
        "feedback_type": "bathroom",
        "expected_status_after_messages": "CLOSED",
    },
    "uncertain_reply": {
        "label": "回答不明确",
        "elder_reply": "嗯……那个……",
        "feedback_type": "unknown",
        "expected_status_after_reply": "CLARIFYING",
    },
}


def scenario_messages(scenario_code: str, elder_id: str = "E001") -> list[dict[str, Any]]:
    if scenario_code not in SCENARIO_EXPECTATIONS:
        allowed = ", ".join(sorted(SCENARIO_EXPECTATIONS))
        raise ValueError(f"unknown scenario_code; expected one of: {allowed}")

    if scenario_code == "no_response":
        return [
            leave_bed_message(elder_id, scenario_code, no_body_seconds=360, radar_movement=True),
            no_response_timeout_message(elder_id),
        ]
    if scenario_code == "fall_detected":
        return [
            leave_bed_message(elder_id, scenario_code, no_body_seconds=180, radar_movement=True),
            fall_detected_message(elder_id),
        ]
    if scenario_code == "return_to_bed":
        return [
            leave_bed_message(elder_id, scenario_code, no_body_seconds=180, radar_movement=True),
            return_to_bed_message(elder_id),
        ]
    if scenario_code == "dizzy":
        return [leave_bed_message(elder_id, scenario_code, no_body_seconds=220, radar_movement=True)]
    if scenario_code == "need_help":
        return [leave_bed_message(elder_id, scenario_code, no_body_seconds=240, radar_movement=True)]
    return [leave_bed_message(elder_id, scenario_code, no_body_seconds=180, radar_movement=True)]


def scenario_payload(scenario_code: str, elder_id: str = "E001") -> dict[str, Any]:
    expectation = SCENARIO_EXPECTATIONS.get(scenario_code)
    if expectation is None:
        allowed = ", ".join(sorted(SCENARIO_EXPECTATIONS))
        raise ValueError(f"unknown scenario_code; expected one of: {allowed}")
    return {
        "scenario_code": scenario_code,
        "elder_id": elder_id,
        "expectation": expectation,
        "messages": scenario_messages(scenario_code, elder_id),
    }
