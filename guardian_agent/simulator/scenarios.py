from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .event_factory import guardian_message


ROOT_DIR = Path(__file__).resolve().parent.parent
SCENARIO_CONTRACT_PATH = ROOT_DIR / "contracts" / "scenarios_v1.json"


def _load_scenario_contract() -> dict[str, Any]:
    with SCENARIO_CONTRACT_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


SCENARIO_CONTRACT = _load_scenario_contract()
SCENARIO_DEFINITIONS = {
    scenario["code"]: scenario for scenario in SCENARIO_CONTRACT["scenarios"]
}
SCENARIO_EXPECTATIONS = {
    code: {
        "label": scenario["name"],
        "elder_reply": scenario["elder_reply"],
        "expected_intent": scenario["expected_intent"],
        "expected_status": scenario["expected_status"],
        "expected_risk": scenario["expected_risk"],
        "final_status": scenario["final_status"],
    }
    for code, scenario in SCENARIO_DEFINITIONS.items()
}


def scenario_messages(scenario_code: str, elder_id: str = "E001") -> list[dict[str, Any]]:
    scenario = SCENARIO_DEFINITIONS.get(scenario_code)
    if scenario is None:
        allowed = ", ".join(sorted(SCENARIO_DEFINITIONS))
        raise ValueError(f"unknown scenario_code; expected one of: {allowed}")

    return [
        guardian_message(
            event_type=step["event_type"],
            elder_id=elder_id,
            device_type=step["device_type"],
            data=step["data"],
            scenario_code=scenario_code,
        )
        for step in scenario["messages"]
    ]


def scenario_payload(scenario_code: str, elder_id: str = "E001") -> dict[str, Any]:
    scenario = SCENARIO_DEFINITIONS.get(scenario_code)
    if scenario is None:
        allowed = ", ".join(sorted(SCENARIO_DEFINITIONS))
        raise ValueError(f"unknown scenario_code; expected one of: {allowed}")
    return {
        "contract_version": SCENARIO_CONTRACT["contract_version"],
        "scenario_code": scenario_code,
        "elder_id": elder_id,
        "expectation": SCENARIO_EXPECTATIONS[scenario_code],
        "messages": scenario_messages(scenario_code, elder_id),
    }

