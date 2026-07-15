from __future__ import annotations

import json
import unittest
from pathlib import Path

from agent.contracts import (
    CONTRACT_VERSION,
    ElderIntent,
    GuardianEventType,
    NightEventStatus,
    RiskLevel,
    enum_values,
)


ROOT_DIR = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT_DIR / "contracts"
EVALS_DIR = ROOT_DIR / "evals"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


class PhaseZeroContractsTest(unittest.TestCase):
    def test_guardian_message_schema_matches_python_enums(self) -> None:
        schema = load_json(CONTRACTS_DIR / "guardian_message_v1.schema.json")
        self.assertEqual(CONTRACT_VERSION, schema["properties"]["schema_version"]["const"])
        self.assertEqual(
            set(enum_values(GuardianEventType)),
            set(schema["properties"]["event_type"]["enum"]),
        )
        required = set(schema["required"])
        self.assertTrue(
            {
                "schema_version",
                "message_id",
                "source_system",
                "device_type",
                "device_id",
                "elder_id",
                "event_type",
                "occurred_at",
                "data",
                "raw_payload",
            }.issubset(required)
        )

    def test_night_turn_schemas_match_python_enums(self) -> None:
        request_schema = load_json(CONTRACTS_DIR / "night_turn_request_v1.schema.json")
        response_schema = load_json(CONTRACTS_DIR / "night_turn_response_v1.schema.json")
        self.assertEqual(CONTRACT_VERSION, request_schema["properties"]["contract_version"]["const"])
        self.assertEqual(CONTRACT_VERSION, response_schema["properties"]["contract_version"]["const"])
        self.assertEqual(
            set(enum_values(ElderIntent)),
            set(response_schema["properties"]["intent"]["enum"]),
        )
        self.assertEqual(
            set(enum_values(NightEventStatus)),
            set(response_schema["properties"]["event_status"]["enum"]),
        )
        self.assertEqual(
            set(enum_values(RiskLevel)),
            set(response_schema["properties"]["risk_level"]["enum"]),
        )

    def test_exactly_six_core_scenarios_are_defined(self) -> None:
        document = load_json(CONTRACTS_DIR / "scenarios_v1.json")
        scenarios = document["scenarios"]
        self.assertEqual(CONTRACT_VERSION, document["contract_version"])
        self.assertEqual(6, len(scenarios))
        self.assertEqual(
            {
                "normal_bathroom",
                "normal_drink",
                "dizzy",
                "need_help",
                "no_response",
                "fall_detected",
            },
            {scenario["code"] for scenario in scenarios},
        )

        intents = set(enum_values(ElderIntent))
        statuses = set(enum_values(NightEventStatus))
        risks = set(enum_values(RiskLevel))
        event_types = set(enum_values(GuardianEventType))
        for scenario in scenarios:
            self.assertIn(scenario["expected_intent"], intents)
            self.assertIn(scenario["expected_status"], statuses)
            self.assertIn(scenario["final_status"], statuses)
            self.assertIn(scenario["expected_risk"], risks)
            for message in scenario["messages"]:
                self.assertIn(message["event_type"], event_types)
            if scenario["follow_up_event"] is not None:
                self.assertIn(scenario["follow_up_event"], event_types)

    def test_eval_set_has_at_least_thirty_consistent_cases(self) -> None:
        document = load_json(EVALS_DIR / "night_turn_cases_v1.json")
        cases = document["cases"]
        self.assertEqual(CONTRACT_VERSION, document["contract_version"])
        self.assertGreaterEqual(len(cases), 30)
        self.assertEqual(len(cases), len({case["id"] for case in cases}))

        intents = set(enum_values(ElderIntent))
        statuses = set(enum_values(NightEventStatus))
        risks = set(enum_values(RiskLevel))
        for case in cases:
            self.assertIn(case["expected_intent"], intents)
            self.assertIn(case["expected_status"], statuses)
            self.assertIn(case["expected_risk"], risks)
            self.assertIsInstance(case["requires_clarification"], bool)
            self.assertIsInstance(case["must_escalate"], bool)

    def test_eval_set_covers_every_intent_and_danger_overrides(self) -> None:
        cases = load_json(EVALS_DIR / "night_turn_cases_v1.json")["cases"]
        self.assertEqual(
            set(enum_values(ElderIntent)),
            {case["expected_intent"] for case in cases},
        )
        by_id = {case["id"]: case for case in cases}
        self.assertEqual("dizzy", by_id["dizzy_03"]["expected_intent"])
        self.assertTrue(by_id["dizzy_03"]["must_escalate"])
        self.assertEqual("fall", by_id["fall_03"]["expected_intent"])
        self.assertTrue(by_id["fall_03"]["must_escalate"])


if __name__ == "__main__":
    unittest.main()

