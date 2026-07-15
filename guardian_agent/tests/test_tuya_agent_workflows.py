import json
import unittest

import guardian_tools
from agent import db
from agent.seed import seed_demo_data


class TuyaAgentWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        db.init_db(reset=True)
        seed_demo_data(reset=True)

    def test_simulated_scenario_creates_event_for_tuya_agent(self) -> None:
        result = guardian_tools.night_care_workflow(
            action="simulate_guardian_scenario",
            elder_id="E001",
            scenario_code="normal_bathroom",
        )
        active = guardian_tools.night_care_workflow(action="get_active_event", elder_id="E001")

        self.assertEqual(result["action"], "simulate_guardian_scenario")
        self.assertTrue(active["found"])
        self.assertEqual(active["event"]["status"], "WAITING_ELDER_CONFIRM")

    def test_tuya_llm_normalized_reply_bypasses_local_conversation(self) -> None:
        guardian_tools.night_care_workflow(
            action="simulate_guardian_scenario",
            elder_id="E001",
            scenario_code="normal_bathroom",
        )
        result = guardian_tools.night_care_workflow(
            action="handle_elder_reply",
            elder_id="E001",
            feedback_type="bathroom",
            original_text="我去趟卫生间，不用担心",
            confidence="0.91",
        )

        self.assertEqual(result["event"]["status"], "MONITORING_RETURN")
        self.assertEqual(result["agent_result"]["provider"], "tuya_agent")
        self.assertEqual(result["agent_result"]["intent"], "bathroom")
        self.assertEqual(result["agent_result"]["confidence"], 0.91)
        self.assertEqual(result["agent_result"]["event_status"], "MONITORING_RETURN")
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT source, request_json, response_json FROM conversation_turns ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["source"], "tuya_agent")
        self.assertIn("我去趟卫生间，不用担心", row["request_json"])
        stored_response = json.loads(row["response_json"])
        self.assertEqual(stored_response["provider"], "tuya_agent")
        self.assertEqual(stored_response["debug"]["engine"], "tuya_agent_mcp")

    def test_tuya_empty_confidence_is_accepted(self) -> None:
        result = guardian_tools.night_care_workflow(
            action="simulate_guardian_scenario",
            elder_id="E001",
            scenario_code="normal_bathroom",
            confidence="",
            timeout_attempts=0,
        )
        self.assertEqual(result["action"], "simulate_guardian_scenario")

    def test_health_workflow_returns_daily_and_weekly_reports(self) -> None:
        daily = guardian_tools.health_report_workflow(action="daily_report", elder_id="E001")
        weekly = guardian_tools.health_report_workflow(action="weekly_report", elder_id="E001")

        self.assertTrue(daily["found"])
        self.assertTrue(weekly["found"])


if __name__ == "__main__":
    unittest.main()
