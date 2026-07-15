import unittest

from agent.voice import SAFETY_ALERT_TEXT, voice_alert_command


class VoiceAlertCommandTest(unittest.TestCase):
    def test_critical_escalation_starts_repeating_alert(self) -> None:
        command = voice_alert_command(
            {"id": "evt-fall", "elder_id": "E001", "status": "ESCALATED", "risk_level": "CRITICAL"}
        )

        self.assertEqual(command["action"], "start_repeating")
        self.assertEqual(command["text"], SAFETY_ALERT_TEXT)
        self.assertTrue(command["repeat_policy"]["play_immediately"])
        self.assertEqual(command["repeat_policy"]["after_playback_seconds"], 2)

    def test_return_to_bed_does_not_cancel_escalated_alert(self) -> None:
        command = voice_alert_command(
            {"id": "evt-fall", "elder_id": "E001", "status": "ESCALATED", "risk_level": "CRITICAL"}
        )
        self.assertEqual(command["action"], "start_repeating")

    def test_human_closed_critical_event_stops_alert(self) -> None:
        command = voice_alert_command(
            {"id": "evt-fall", "elder_id": "E001", "status": "CLOSED", "risk_level": "CRITICAL"}
        )
        self.assertEqual(command["action"], "stop")

    def test_non_critical_event_has_no_voice_alert(self) -> None:
        command = voice_alert_command(
            {"id": "evt-normal", "elder_id": "E001", "status": "MONITORING_RETURN", "risk_level": "WARNING"}
        )
        self.assertIsNone(command)


if __name__ == "__main__":
    unittest.main()
