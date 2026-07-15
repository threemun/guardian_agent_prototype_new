from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import db
from agent.message import normalize_guardian_message, process_guardian_message
from agent.night import NightCareAgent
from agent.seed import seed_demo_data
from simulator.scenarios import scenario_payload


class GuardianMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "guardian-message-test.sqlite3"
        seed_demo_data(reset=True)

    def tearDown(self) -> None:
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_normalize_guardian_message_requires_contract_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema_version is required"):
            normalize_guardian_message(
                {
                    "message_id": "msg-001",
                    "elder_id": "E001",
                    "event_type": "LEAVE_BED",
                    "data": {"no_body_seconds": 180},
                }
            )

    def test_normalize_guardian_message_accepts_v1_contract(self) -> None:
        message = normalize_guardian_message(self._leave_bed_payload("msg-valid-001"))

        self.assertEqual(message["schema_version"], "1.0")
        self.assertEqual(message["source_system"], "simulator")
        self.assertEqual(message["device_type"], "sleep_band")
        self.assertEqual(message["event_type"], "LEAVE_BED")
        self.assertIn("received_at", message)

    def test_leave_bed_message_creates_event_once(self) -> None:
        payload = self._leave_bed_payload("sleep-E001-test-001")

        with db.get_conn() as conn:
            before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            first = process_guardian_message(conn, payload)
            second = process_guardian_message(conn, payload)
            after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(after, before + 1)
        self.assertEqual(second["event"]["id"], first["event"]["id"])

    def test_raw_payload_and_message_id_are_kept_in_input_timeline(self) -> None:
        payload = self._leave_bed_payload("sleep-E001-timeline-001")

        with db.get_conn() as conn:
            result = process_guardian_message(conn, payload)
            raw = conn.execute(
                "SELECT * FROM raw_messages WHERE message_id = ?",
                (payload["message_id"],),
            ).fetchone()

        self.assertEqual(raw["processed_status"], "processed")
        input_step = result["event"]["timeline"][0]
        self.assertEqual(input_step["step_type"], "input")
        self.assertEqual(input_step["result"]["message_id"], payload["message_id"])
        self.assertEqual(input_step["result"]["raw_payload"], payload["raw_payload"])

    def test_return_to_bed_message_closes_monitoring_event(self) -> None:
        with db.get_conn() as conn:
            agent = NightCareAgent(conn)
            event = agent.trigger_possible_leave_bed("E001")
            event = agent.apply_feedback(event["id"], "bathroom", "我去洗手间")
            self.assertEqual(event["status"], "MONITORING_RETURN")
            result = process_guardian_message(
                conn,
                {
                    "schema_version": "1.0",
                    "message_id": "return-E001-test-001",
                    "source_system": "test",
                    "device_type": "sleep_band",
                    "device_id": "SLEEP-E001",
                    "elder_id": "E001",
                    "event_type": "RETURN_TO_BED",
                    "occurred_at": "2026-07-14T02:20:20+08:00",
                    "data": {"event_id": event["id"], "detail": "测试确认返床。"},
                    "raw_payload": {"test_case": "return_to_bed"},
                },
            )

        self.assertEqual(result["event"]["status"], "CLOSED")
        self.assertEqual(result["processed_action"], "confirmed_return_to_bed")

    def test_scenario_payload_uses_guardian_message_contract(self) -> None:
        payload = scenario_payload("fall_detected", "E003")

        self.assertEqual(payload["scenario_code"], "fall_detected")
        self.assertEqual(payload["messages"][0]["event_type"], "FALL_DETECTED")
        self.assertEqual(payload["messages"][0]["schema_version"], "1.0")

    def test_all_scenarios_generate_valid_guardian_messages(self) -> None:
        expected_codes = {
            "normal_bathroom",
            "normal_drink",
            "dizzy",
            "need_help",
            "no_response",
            "fall_detected",
        }
        for code in expected_codes:
            payload = scenario_payload(code, "E001")
            for message in payload["messages"]:
                self.assertEqual(normalize_guardian_message(message)["schema_version"], "1.0")

    @staticmethod
    def _leave_bed_payload(message_id: str) -> dict:
        return {
            "schema_version": "1.0",
            "message_id": message_id,
            "source_system": "simulator",
            "device_type": "sleep_band",
            "device_id": "SLEEP001",
            "elder_id": "E001",
            "event_type": "LEAVE_BED",
            "occurred_at": "2026-07-14T02:13:20+08:00",
            "data": {"no_body_seconds": 180, "radar_movement": True, "location": "卧室"},
            "raw_payload": {"scenario_code": "normal_bathroom"},
        }


if __name__ == "__main__":
    unittest.main()
