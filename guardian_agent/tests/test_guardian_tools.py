from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent import db
from agent.seed import seed_demo_data
import guardian_tools


class GuardianToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "guardian-test.sqlite3"
        seed_demo_data(reset=True)

    def tearDown(self) -> None:
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_list_elders_returns_three_demo_elders(self) -> None:
        result = guardian_tools.list_elders()

        self.assertEqual(len(result["items"]), 3)
        self.assertEqual({item["id"] for item in result["items"]}, {"E001", "E002", "E003"})

    def test_get_active_event_returns_existing_event(self) -> None:
        result = guardian_tools.get_active_event("E001")

        self.assertTrue(result["found"])
        self.assertEqual(result["event"]["elder_id"], "E001")
        self.assertNotEqual(result["event"]["status"], "CLOSED")

    def test_submit_feedback_records_original_text_and_source(self) -> None:
        event = guardian_tools.get_active_event("E001")["event"]

        result = guardian_tools.submit_elder_feedback(
            event_id=event["id"],
            elder_id="E001",
            feedback_type="bathroom",
            original_text="我去一下洗手间",
            source="tuya_agent",
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["event"]["status"], "MONITORING_RETURN")
        feedback_step = next(
            step for step in result["event"]["timeline"] if step["step_type"] == "feedback"
        )
        self.assertEqual(feedback_step["result"]["original_text"], "我去一下洗手间")
        self.assertEqual(feedback_step["result"]["source"], "tuya_agent")

    def test_invalid_feedback_type_is_rejected(self) -> None:
        event = guardian_tools.get_active_event("E001")["event"]

        with self.assertRaisesRegex(ValueError, "invalid feedback_type"):
            guardian_tools.submit_elder_feedback(event["id"], "unknown")

    def test_elder_event_mismatch_is_rejected(self) -> None:
        event = guardian_tools.get_active_event("E001")["event"]

        with self.assertRaisesRegex(ValueError, "does not belong"):
            guardian_tools.submit_elder_feedback(
                event_id=event["id"],
                elder_id="E002",
                feedback_type="ok",
            )

    def test_device_action_is_added_to_timeline(self) -> None:
        event = guardian_tools.get_active_event("E001")["event"]

        result = guardian_tools.record_device_action(
            event_id=event["id"],
            action="open_night_light",
            success=True,
            detail="涂鸦卧室夜灯已打开。",
        )

        self.assertTrue(result["recorded"])
        latest = result["event"]["timeline"][-1]
        self.assertEqual(latest["result"]["action"], "open_night_light")
        self.assertTrue(latest["result"]["success"])

    def test_daily_reports_exist_for_each_elder(self) -> None:
        for elder_id in ("E001", "E002", "E003"):
            result = guardian_tools.get_daily_report(elder_id)
            self.assertTrue(result["found"])
            self.assertEqual(result["elder_id"], elder_id)
            self.assertEqual(result["report_type"], "daily")
            self.assertIn("report_note", result)

    def test_generate_weekly_report_returns_structured_report(self) -> None:
        result = guardian_tools.generate_weekly_report("E001")

        self.assertTrue(result["found"])
        self.assertEqual(result["elder_id"], "E001")
        self.assertEqual(result["report_type"], "weekly")
        self.assertIn("key_findings", result["content"])
        self.assertIn("suggestions", result["content"])

    def test_recent_vitals_returns_elder_specific_rows(self) -> None:
        result = guardian_tools.get_recent_vitals("E003", limit=5)

        self.assertEqual(result["count"], 5)
        self.assertTrue(all(item["elder_id"] == "E003" for item in result["items"]))

    def test_night_care_workflow_handles_elder_reply(self) -> None:
        result = guardian_tools.night_care_workflow(
            action="handle_elder_reply",
            elder_id="E002",
            feedback_type="drink",
            original_text="我起来喝口水",
        )

        self.assertEqual(result["workflow"], "night_care")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["event"]["status"], "MONITORING_RETURN")

    def test_night_care_workflow_can_query_timeline(self) -> None:
        event = guardian_tools.get_active_event("E001")["event"]

        result = guardian_tools.night_care_workflow(
            action="get_event_timeline",
            event_id=event["id"],
        )

        self.assertEqual(result["workflow"], "night_care")
        self.assertEqual(result["event_id"], event["id"])
        self.assertGreater(len(result["items"]), 0)

    def test_health_report_workflow_returns_weekly_report(self) -> None:
        result = guardian_tools.health_report_workflow(action="weekly_report", elder_id="E001")

        self.assertEqual(result["workflow"], "health_report")
        self.assertTrue(result["found"])
        self.assertEqual(result["report_type"], "weekly")

    def test_health_report_workflow_refreshes_all_reports(self) -> None:
        result = guardian_tools.health_report_workflow(
            action="refresh_all_reports",
            elder_id="E003",
            limit=3,
        )

        self.assertEqual(result["workflow"], "health_report")
        self.assertEqual(result["daily_report"]["report_type"], "daily")
        self.assertEqual(result["weekly_report"]["report_type"], "weekly")
        self.assertEqual(result["recent_vitals"]["count"], 3)


if __name__ == "__main__":
    unittest.main()
