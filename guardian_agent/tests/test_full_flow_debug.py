from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import db
from agent.conversation import handle_night_turn
from agent.debug_timers import DebugTimerRegistry
from agent.night import NightCareAgent
from agent.seed import seed_demo_data
from server import DEBUG_TIMERS, dashboard_payload, fire_debug_timeout


class FullFlowDebugTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "full-flow-debug-test.sqlite3"
        DEBUG_TIMERS.cancel_all()
        seed_demo_data(reset=True)

    def tearDown(self) -> None:
        DEBUG_TIMERS.cancel_all()
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_conversation_returns_agent_contract_and_is_persisted(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed("E001")
            result = handle_night_turn(
                conn,
                {
                    "elder_id": "E001",
                    "event_id": event["id"],
                    "session_id": "debug-session-1",
                    "text": "我去趟卫生间，不用担心",
                    "source": "web_debug",
                },
            )
            dashboard = dashboard_payload(conn, "E001", event["id"])

        self.assertEqual(result["agent_result"]["contract_version"], "1.0")
        self.assertEqual(result["agent_result"]["intent"], "bathroom")
        self.assertEqual(result["agent_result"]["event_status"], "MONITORING_RETURN")
        self.assertTrue(result["debug"]["temporary_agent_substitute"])
        self.assertEqual(len(dashboard["conversation_turns"]), 1)
        self.assertEqual(dashboard["conversation_turns"][0]["request"]["text"], "我去趟卫生间，不用担心")

    def test_debug_timeout_uses_standard_message_and_updates_state(self) -> None:
        with db.get_conn() as conn:
            event = NightCareAgent(conn).trigger_possible_leave_bed("E001")

        fire_debug_timeout(
            {
                "event_id": event["id"],
                "elder_id": "E001",
                "seconds": 1.0,
                "attempts": 2,
                "timeout_kind": "elder_response",
            }
        )

        with db.get_conn() as conn:
            updated = NightCareAgent(conn).get_event(event["id"])
            raw = conn.execute(
                "SELECT * FROM raw_messages WHERE topic = 'guardian.no_response_timeout' ORDER BY id DESC LIMIT 1"
            ).fetchone()

        self.assertEqual(updated["status"], "WAITING_FAMILY_CONFIRM")
        self.assertIsNotNone(raw)
        self.assertEqual(raw["source"], "debug_timer")

    def test_timer_registry_reports_remaining_time_and_cancellation(self) -> None:
        registry = DebugTimerRegistry()
        timer = registry.start(
            event_id="evt_test",
            seconds=10,
            attempts=1,
            timeout_kind="elder_response",
            callback=lambda _: None,
            context={"elder_id": "E001"},
        )

        self.assertEqual(timer["status"], "active")
        self.assertGreater(timer["remaining_seconds"], 0)
        self.assertEqual(timer["elder_id"], "E001")
        cancelled = registry.cancel("evt_test")
        self.assertEqual(cancelled["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
