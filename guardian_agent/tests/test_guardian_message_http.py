from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent import db
from agent.seed import seed_demo_data
from server import AppHandler
from simulator.scenarios import scenario_payload


class GuardianMessageHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_db_path = db.DB_PATH
        self._temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db.DB_PATH = Path(self._temp_dir.name) / "guardian-http-test.sqlite3"
        seed_demo_data(reset=True)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), AppHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        db.DB_PATH = self._original_db_path
        self._temp_dir.cleanup()

    def test_post_guardian_message_is_idempotent(self) -> None:
        message = scenario_payload("normal_bathroom", "E001")["messages"][0]

        first = self._post_message(message)
        second = self._post_message(message)

        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["event"]["id"], second["event"]["id"])

    def _post_message(self, message: dict) -> dict:
        port = self._server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/guardian/messages",
            data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(200, response.status)
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

