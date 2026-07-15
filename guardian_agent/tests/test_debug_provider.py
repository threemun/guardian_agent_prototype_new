from __future__ import annotations

import unittest

import server


class DebugProviderTest(unittest.TestCase):
    def test_message_contract_reports_conversation_provider(self) -> None:
        contract = server.message_contract()

        self.assertIn(contract["conversation_provider"], {"local_rules", "tuya_agent"})


if __name__ == "__main__":
    unittest.main()
