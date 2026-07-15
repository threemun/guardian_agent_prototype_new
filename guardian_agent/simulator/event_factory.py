from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from agent.contracts import CONTRACT_VERSION


DEVICE_ID_PREFIXES = {
    "sleep_band": "SLEEP",
    "radar": "RADAR",
    "voice_client": "VOICE",
    "simulator": "SIM",
    "system": "GUARDIAN",
}


def guardian_message(
    event_type: str,
    elder_id: str,
    device_type: str,
    data: dict[str, Any],
    scenario_code: str,
    source_system: str = "simulator",
) -> dict[str, Any]:
    """Build one valid GuardianMessage 1.0 from a frozen scenario step."""

    occurred_at = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    prefix = DEVICE_ID_PREFIXES[device_type]
    return {
        "schema_version": CONTRACT_VERSION,
        "message_id": f"{source_system}-{elder_id}-{event_type.lower()}-{uuid.uuid4().hex[:12]}",
        "source_system": source_system,
        "device_type": device_type,
        "device_id": f"{prefix}-{elder_id}",
        "elder_id": elder_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "received_at": occurred_at,
        "data": dict(data),
        "raw_payload": {"scenario_code": scenario_code},
    }

