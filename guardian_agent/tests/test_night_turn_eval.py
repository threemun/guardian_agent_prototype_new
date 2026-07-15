from __future__ import annotations

import unittest

from evals.run_night_turn_eval import load_cases, score_results


class NightTurnEvalScorerTest(unittest.TestCase):
    def test_scorer_accepts_complete_matching_agent_results(self) -> None:
        results = [
            {
                "id": case["id"],
                "intent": case["expected_intent"],
                "status": case["expected_status"],
                "risk": case["expected_risk"],
                "requires_clarification": case["requires_clarification"],
                "must_escalate": case["must_escalate"],
            }
            for case in load_cases()
        ]

        score = score_results(results)

        self.assertEqual(score["total"], 34)
        self.assertEqual(score["passed"], 34)
        self.assertEqual(score["failures"], [])

    def test_scorer_reports_an_agent_mismatch(self) -> None:
        score = score_results(
            [
                {
                    "id": "fall_01",
                    "intent": "ok",
                    "status": "CLOSED",
                    "risk": "INFO",
                    "requires_clarification": False,
                    "must_escalate": False,
                }
            ]
        )

        fall_failure = next(item for item in score["failures"] if item["case"]["id"] == "fall_01")
        self.assertFalse(fall_failure["checks"]["intent"])
        self.assertFalse(fall_failure["checks"]["must_escalate"])


if __name__ == "__main__":
    unittest.main()
