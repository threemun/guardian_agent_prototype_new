from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import db
from agent.conversation import classify_elder_reply, handle_night_turn
from agent.night import NightCareAgent
from agent.seed import seed_demo_data
import guardian_tools


class ConversationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "conversation-test.sqlite3"
        seed_demo_data(reset=True)

    def tearDown(self) -> None:
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_danger_overrides_ok_expression(self) -> None:
        result = classify_elder_reply("我没事，就是有点头晕")

        self.assertEqual(result["intent"], "dizzy")
        self.assertEqual(result["feedback_type"], "dizzy")
        self.assertFalse(result["requires_clarification"])

    def test_night_turn_records_bathroom_reply(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed("E001")
            result = handle_night_turn(
                conn,
                {
                    "elder_id": "E001",
                    "event_id": event["id"],
                    "text": "我去趟卫生间，不用担心",
                    "source": "voice_lab",
                },
            )

        self.assertEqual(result["intent"], "bathroom")
        self.assertEqual(result["event_status"], "MONITORING_RETURN")
        self.assertIn("安全回床", result["reply_text"])

    def test_night_turn_escalates_help_request(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed("E001")
            result = handle_night_turn(
                conn,
                {
                    "elder_id": "E001",
                    "event_id": event["id"],
                    "text": "我腿没劲，扶我一下",
                    "source": "voice_lab",
                },
            )

        self.assertEqual(result["intent"], "need_help")
        self.assertEqual(result["event_status"], "WAITING_FAMILY_CONFIRM")
        self.assertEqual(result["risk_level"], "CRITICAL")

    def test_unknown_reply_enters_clarifying_state(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed("E001")
            result = handle_night_turn(
                conn,
                {
                    "elder_id": "E001",
                    "event_id": event["id"],
                    "text": "嗯……那个……",
                    "source": "voice_lab",
                },
            )

        self.assertEqual(result["intent"], "unknown")
        self.assertTrue(result["requires_clarification"])
        self.assertEqual(result["event_status"], "CLARIFYING")

    def test_mcp_workflow_can_handle_raw_night_turn_text(self) -> None:
        result = guardian_tools.night_care_workflow(
            action="night_turn",
            elder_id="E002",
            original_text="我起来喝口水",
            source="tuya_agent",
        )

        self.assertEqual(result["workflow"], "night_care")
        self.assertEqual(result["intent"], "drink")
        self.assertEqual(result["event_status"], "MONITORING_RETURN")


if __name__ == "__main__":
    unittest.main()
