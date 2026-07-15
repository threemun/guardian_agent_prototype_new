from __future__ import annotations

from typing import Any


SAFETY_ALERT_TEXT = "检测到您存在安全问题，我已联系您的子女"
ACTIVE_ALERT_STATUSES = {"WAITING_FAMILY_CONFIRM", "ESCALATED"}


def voice_alert_command(event: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build the command contract consumed by a future elder-side TTS adapter."""
    if not event or event.get("risk_level") != "CRITICAL":
        return None

    event_id = str(event["id"])
    base = {
        "contract_version": "1.0",
        "command_type": "safety_voice_alert",
        "alert_id": f"voice-alert-{event_id}",
        "event_id": event_id,
        "elder_id": event["elder_id"],
    }
    if event.get("status") == "CLOSED":
        return {**base, "action": "stop", "reason": "event_closed_by_human"}
    if event.get("status") not in ACTIVE_ALERT_STATUSES:
        return None

    return {
        **base,
        "action": "start_repeating",
        "text": SAFETY_ALERT_TEXT,
        "language": "zh-CN",
        "repeat_policy": {
            "play_immediately": True,
            "after_playback_seconds": 2,
            "until": "human_confirmation_or_event_closed",
        },
        "adapter_status": "reserved_not_connected",
    }
