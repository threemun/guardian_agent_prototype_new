from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import db
from agent.night import NightCareAgent
from agent.seed import seed_demo_data


class NightStateMachineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "night-state-machine-test.sqlite3"
        seed_demo_data(reset=True)

    def tearDown(self) -> None:
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_leave_bed_always_waits_for_elder_before_timeout_event(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed(
                "E001",
                scenario="no_response",
                signals={
                    "sleep_band_no_body_seconds": 600,
                    "radar_movement": False,
                    "night_time": True,
                },
            )

        self.assertEqual(event["status"], "WAITING_ELDER_CONFIRM")
        self.assertEqual(event["risk_level"], "WARNING")

    def test_ok_requires_return_signal_before_closing(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "ok", "我没事")
            self.assertEqual(event["status"], "MONITORING_RETURN")
            self.assertIsNone(event["closed_at"])

            event = agent.confirm_return_to_bed(event["id"], source="simulator")

        self.assertEqual(event["status"], "CLOSED")
        self.assertIsNotNone(event["closed_at"])

    def test_monitoring_timeout_escalates_to_family(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "bathroom", "我去卫生间")
            self.assertEqual(event["status"], "MONITORING_RETURN")

            event = agent.simulate_timeout(event["id"], source="test")

        self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")
        self.assertEqual(event["risk_level"], "CRITICAL")

    def test_only_one_unclear_reply_is_allowed(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "unknown", "嗯……那个……")
            self.assertEqual(event["status"], "CLARIFYING")

            event = agent.apply_feedback(event["id"], "unknown", "我也说不清楚")

        self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")
        self.assertEqual(event["risk_level"], "CRITICAL")

    def test_first_timeout_clarifies_and_second_timeout_escalates(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.simulate_timeout(event["id"], attempts=1, source="test")
            self.assertEqual(event["status"], "CLARIFYING")

            event = agent.simulate_timeout(event["id"], attempts=2, source="test")

        self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")

    def test_low_confidence_is_treated_as_unknown(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(
                event["id"],
                "bathroom",
                "可能去一下",
                source="tuya_agent",
                confidence=0.4,
            )

        self.assertEqual(event["status"], "CLARIFYING")
        feedback_step = next(step for step in event["timeline"] if step["step_type"] == "feedback")
        self.assertEqual(feedback_step["result"]["requested_feedback_type"], "bathroom")
        self.assertEqual(feedback_step["result"]["feedback_type"], "unknown")

    def test_dangerous_text_overrides_ok(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(
                event["id"],
                "ok",
                "我没事，就是胸痛，喘不过气",
                source="tuya_agent",
                confidence=0.95,
            )

        self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")
        self.assertEqual(event["risk_level"], "CRITICAL")
        feedback_step = next(step for step in event["timeline"] if step["step_type"] == "feedback")
        self.assertTrue(feedback_step["result"]["safety_override"])

    def test_fall_feedback_escalates_directly(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "fall", "我摔倒了", source="tuya_agent")

        self.assertEqual(event["status"], "ESCALATED")
        self.assertEqual(event["risk_level"], "CRITICAL")

    def test_high_risk_event_cannot_be_downgraded_or_agent_closed(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "dizzy", "我头晕")
            event = agent.apply_feedback(event["id"], "ok", "现在没事了")
            self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")

            event = agent.confirm_return_to_bed(event["id"], source="simulator")
            self.assertEqual(event["status"], "WAITING_FAMILY_CONFIRM")

            with self.assertRaisesRegex(ValueError, "human confirmation"):
                agent.close_event(event["id"], source="tuya_agent", confirmed_by_human=False)

            event = agent.close_event(event["id"], source="web_console", confirmed_by_human=True)

        self.assertEqual(event["status"], "CLOSED")


if __name__ == "__main__":
    unittest.main()
