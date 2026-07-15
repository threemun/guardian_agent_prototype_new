from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any


class DebugTimerRegistry:
    """In-memory accelerated timers for the local full-flow console."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._timers: dict[str, threading.Timer] = {}

    def start(
        self,
        event_id: str,
        seconds: float,
        attempts: int,
        timeout_kind: str,
        callback: Callable[[dict[str, Any]], None],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if seconds <= 0:
            raise ValueError("timer seconds must be greater than 0")
        if attempts < 1:
            raise ValueError("timer attempts must be at least 1")
        self.cancel(event_id)
        record = {
            "event_id": event_id,
            "seconds": float(seconds),
            "attempts": int(attempts),
            "timeout_kind": timeout_kind,
            "deadline_epoch": time.time() + float(seconds),
            "status": "active",
            "error": "",
            **(context or {}),
        }

        def fire() -> None:
            with self._lock:
                current = self._records.get(event_id)
                if current is not record or current["status"] != "active":
                    return
                current["status"] = "firing"
            try:
                callback(dict(record))
                with self._lock:
                    record["status"] = "fired"
            except Exception as exc:
                with self._lock:
                    record["status"] = "error"
                    record["error"] = str(exc)

        timer = threading.Timer(float(seconds), fire)
        timer.daemon = True
        with self._lock:
            self._records[event_id] = record
            self._timers[event_id] = timer
        timer.start()
        return self.get(event_id)

    def get(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(event_id)
            if not record:
                return None
            result = dict(record)
        remaining = max(0.0, result["deadline_epoch"] - time.time())
        result["remaining_seconds"] = math.ceil(remaining * 10) / 10
        return result

    def cancel(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            timer = self._timers.pop(event_id, None)
            record = self._records.get(event_id)
            if record and record["status"] in {"active", "firing"}:
                record["status"] = "cancelled"
        if timer:
            timer.cancel()
        return self.get(event_id)

    def cancel_all(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
            for record in self._records.values():
                if record["status"] in {"active", "firing"}:
                    record["status"] = "cancelled"
        for timer in timers:
            timer.cancel()
