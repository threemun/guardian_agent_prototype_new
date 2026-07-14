from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent.db import DB_PATH, get_conn, init_db, row_to_dict, rows_to_dicts, today_str
from agent.health import HealthAgent
from agent.memory import MemoryAgent
from agent.night import NightCareAgent, STATUS_LABELS
from agent.seed import seed_demo_data


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"


def ensure_db() -> None:
    init_db(reset=False)
    if not DB_PATH.exists():
        seed_demo_data(reset=True)
        return
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM elders").fetchone()[0]
    if count == 0:
        seed_demo_data(reset=True)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "GuardianAgentHTTP/0.1"

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            self._send_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
            return
        if parsed.path.startswith("/api/v1/recordings/") and parsed.path.endswith("/audio"):
            try:
                self._send_recording_audio(parsed.path)
            except Exception as exc:
                self._send_error(exc)
            return
        try:
            data = self._route_get(parsed.path, parse_qs(parsed.query))
            self._send_json(data)
        except Exception as exc:
            self._send_error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            data = self._route_post(parsed.path, body)
            self._send_json(data)
        except Exception as exc:
            self._send_error(exc)

    def _route_get(self, path: str, query: dict[str, list[str]]) -> dict:
        elder_id = query.get("elder_id", ["E001"])[0]
        with get_conn() as conn:
            if path == "/api/v1/dashboard":
                selected_event_id = query.get("selected_event_id", [""])[0]
                return dashboard_payload(conn, elder_id, selected_event_id)
            if path == "/api/v1/elders":
                rows = conn.execute("SELECT * FROM elders ORDER BY id").fetchall()
                return {"items": rows_to_dicts(rows)}
            if path == "/api/v1/events":
                rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
                events = [decorate_event(conn, row_to_dict(row)) for row in rows]
                return {"items": events}
            if path.startswith("/api/v1/events/"):
                event_id = path.split("/")[4]
                agent = NightCareAgent(conn)
                event = agent.get_event(event_id)
                if not event:
                    raise ValueError("event not found")
                if path.endswith("/timeline"):
                    return {"items": event["timeline"]}
                return event
            if path == "/api/v1/vitals":
                limit = int(query.get("limit", ["14"])[0])
                return {"items": HealthAgent(conn).latest_vitals(elder_id, limit)}
            if path == "/api/v1/reports/daily":
                return {"item": HealthAgent(conn).latest_report(elder_id, "daily")}
            if path == "/api/v1/reports/weekly":
                return {"item": HealthAgent(conn).latest_report(elder_id, "weekly")}
            if path == "/api/v1/memories":
                agent = MemoryAgent(conn)
                memory_start_date = query.get("memory_start_date", query.get("start_date", [""]))[0]
                memory_end_date = query.get("memory_end_date", query.get("end_date", [""]))[0]
                return {
                    "items": agent.search_memories(
                        query=query.get("query", [""])[0],
                        person=query.get("person", [""])[0],
                        emotion=query.get("emotion", [""])[0],
                        topic=query.get("topic", [""])[0],
                        memory_start_date=memory_start_date,
                        memory_end_date=memory_end_date,
                        recorded_start_date=query.get("recorded_start_date", [""])[0],
                        recorded_end_date=query.get("recorded_end_date", [""])[0],
                        elder_id=elder_id,
                    ),
                    "facets": agent.facets(elder_id),
                }
            if path == "/api/v1/memories/recordings":
                return {"items": MemoryAgent(conn).latest_recordings(elder_id)}
            if path == "/api/v1/memories/facets":
                return MemoryAgent(conn).facets(elder_id)
            if path == "/api/v1/message-contract":
                return message_contract()
        raise ValueError(f"unknown route: {path}")

    def _route_post(self, path: str, body: dict) -> dict:
        if path == "/api/v1/mock/reset":
            seed_demo_data(reset=True)
            with get_conn() as conn:
                return dashboard_payload(conn, "E001")

        with get_conn() as conn:
            night_agent = NightCareAgent(conn)
            health_agent = HealthAgent(conn)
            memory_agent = MemoryAgent(conn)
            if path == "/api/v1/messages":
                message_type = body.get("message_type") or body.get("event_type")
                if message_type in {"sensor_event", "POSSIBLE_LEAVE_BED", "SOS_BUTTON"}:
                    return {"accepted": True, "event": night_agent.ingest_sensor_message(body)}
                if message_type in {"vitals_record", "daily_health_data"}:
                    vital = health_agent.record_vitals(body.get("elder_id", "E001"), body.get("data", body))
                    report = health_agent.generate_daily_report(body.get("elder_id", "E001"))
                    return {"accepted": True, "vital": vital, "daily_report": report}
                if message_type in {"call_recording", "audio_recording"}:
                    return {"accepted": True, **memory_agent.ingest_call_recording(body)}
                raise ValueError("unsupported message_type")
            if path == "/api/v1/mock/night-leave-bed":
                return {"event": night_agent.trigger_possible_leave_bed(body.get("elder_id", "E001"), body.get("scenario", "standard"))}
            if path == "/api/v1/mock/sos":
                return {"event": night_agent.trigger_sos(body.get("elder_id", "E003"), body.get("location", "客厅"))}
            if path == "/api/v1/mock/health-abnormal":
                elder_id = body.get("elder_id", "E001")
                report = health_agent.record_mock_abnormal(elder_id)
                return {"daily_report": report, "event": night_agent.trigger_health_abnormal(elder_id, report)}
            if path == "/api/v1/mock/memory-call":
                return memory_agent.create_mock_memory(body.get("mock_key", "mom_childhood_courtyard"), body.get("elder_id"))
            if path == "/api/v1/reports/daily/generate":
                return {"item": health_agent.generate_daily_report(body.get("elder_id", "E001"), body.get("report_date"))}
            if path == "/api/v1/reports/weekly/generate":
                return {"item": health_agent.generate_weekly_report(body.get("elder_id", "E001"), body.get("week_end"))}
            if path.startswith("/api/v1/events/"):
                parts = path.split("/")
                event_id = parts[4]
                action = parts[5] if len(parts) > 5 else ""
                if action == "feedback":
                    return {"event": night_agent.apply_feedback(event_id, body.get("feedback_type", "ok"))}
                if action == "timeout":
                    return {"event": night_agent.simulate_timeout(event_id)}
                if action == "close":
                    return {"event": night_agent.close_event(event_id)}
        raise ValueError(f"unknown route: {path}")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path, content_type: str | None = None, allow_range: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        content_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        if allow_range:
            range_header = self.headers.get("Range", "")
            if range_header.startswith("bytes="):
                start, end = parse_range_header(range_header, len(data))
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(chunk)
                return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if allow_range:
            self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_recording_audio(self, path: str) -> None:
        recording_id = path.split("/")[4]
        with get_conn() as conn:
            row = conn.execute("SELECT audio_uri FROM call_recordings WHERE id = ?", (recording_id,)).fetchone()
        if row is None:
            raise ValueError("recording not found")
        audio_path = Path(row["audio_uri"])
        if not audio_path.is_absolute():
            audio_path = ROOT_DIR / audio_path
        audio_path = audio_path.resolve()
        try:
            audio_path.relative_to(ROOT_DIR)
        except ValueError as exc:
            raise ValueError("recording audio is outside the local prototype directory") from exc
        self._send_file(audio_path, content_type="audio/wav", allow_range=True)

    def _send_error(self, exc: Exception) -> None:
        traceback.print_exc()
        self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args) -> None:
        return


def dashboard_payload(conn, elder_id: str, selected_event_id: str = "") -> dict:
    health_agent = HealthAgent(conn)
    memory_agent = MemoryAgent(conn)
    events = [decorate_event(conn, row_to_dict(row)) for row in conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()]
    selected = next((event for event in events if event["id"] == selected_event_id), None)
    if selected is None:
        selected = next((event for event in events if event["elder_id"] == elder_id), None) or (events[0] if events else None)
    if selected:
        selected = NightCareAgent(conn).get_event(selected["id"])
    counts = {
        "today_events": len(events),
        "waiting_elder": sum(1 for event in events if event["status"] == "WAITING_ELDER_CONFIRM"),
        "escalated": sum(1 for event in events if event["risk_level"] == "CRITICAL" and event["status"] != "CLOSED"),
        "closed": sum(1 for event in events if event["status"] == "CLOSED"),
    }
    return {
        "mode": "Mock 演示模式",
        "version": "v0.1.0",
        "selected_elder_id": elder_id,
        "counts": counts,
        "events": events,
        "selected_event": selected,
        "daily_report": health_agent.latest_report(elder_id, "daily"),
        "weekly_report": health_agent.latest_report(elder_id, "weekly"),
        "vitals": health_agent.latest_vitals(elder_id, 7),
        "memories": memory_agent.search_memories(elder_id=elder_id, limit=8),
        "memory_facets": memory_agent.facets(elder_id),
        "memory_recordings": memory_agent.latest_recordings(elder_id, 8),
        "contract": message_contract(),
    }


def decorate_event(conn, event: dict | None) -> dict | None:
    if not event:
        return None
    elder = row_to_dict(conn.execute("SELECT * FROM elders WHERE id = ?", (event["elder_id"],)).fetchone())
    event["elder"] = elder
    event["status_label"] = STATUS_LABELS.get(event["status"], event["status"])
    event["risk_badge"] = event["risk_level"]
    event["tool_count"] = len(event.get("tools", []))
    return event


def parse_range_header(range_header: str, total_size: int) -> tuple[int, int]:
    raw = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
    start_text, _, end_text = raw.partition("-")
    if start_text == "":
        suffix = int(end_text or "0")
        start = max(0, total_size - suffix)
        end = total_size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else total_size - 1
    if start < 0 or end < start or start >= total_size:
        raise ValueError("invalid audio range")
    return start, min(end, total_size - 1)


def message_contract() -> dict:
    return {
        "ingest_endpoint": "POST /api/v1/messages",
        "result_endpoints": [
            "GET /api/v1/events",
            "GET /api/v1/events/{event_id}",
            "GET /api/v1/events/{event_id}/timeline",
            "GET /api/v1/reports/daily",
            "GET /api/v1/reports/weekly",
            "GET /api/v1/memories?elder_id=&query=&person=&emotion=&memory_start_date=&memory_end_date=&recorded_start_date=&recorded_end_date=",
            "GET /api/v1/memories/recordings",
            "GET /api/v1/recordings/{recording_id}/audio",
        ],
        "supported_messages": [
            {
                "message_type": "sensor_event",
                "event_type": "POSSIBLE_LEAVE_BED",
                "required_fields": ["message_id", "elder_id", "event_type", "timestamp", "signals"],
                "signals": ["sleep_band_no_body_seconds", "radar_movement", "night_time", "ambient_light"],
            },
            {
                "message_type": "sensor_event",
                "event_type": "SOS_BUTTON",
                "required_fields": ["message_id", "elder_id", "event_type", "timestamp", "location"],
            },
            {
                "message_type": "vitals_record",
                "required_fields": ["message_id", "elder_id", "measured_at", "data"],
                "data_fields": [
                    "temperature",
                    "heart_rate",
                    "systolic_bp",
                    "diastolic_bp",
                    "fasting_glucose",
                    "blood_oxygen",
                    "sleep_hours",
                    "sleep_quality",
                    "steps",
                ],
            },
            {
                "message_type": "call_recording",
                "required_fields": ["message_id", "elder_id", "call_started_at", "audio_uri"],
                "optional_fields": ["family_member", "audio_duration_seconds", "transcript", "mock_key", "memory_date"],
                "notes": "audio_uri can be a local path, object storage URL, or temporary upload URL. If transcript is provided, the STT step is skipped.",
            },
        ],
        "event_status": list(STATUS_LABELS.keys()),
        "report_note": "Agent 分析结果和老人事件记录均已通过接口暴露给网页端，后续可替换为真实服务器推送。",
    }


def main() -> None:
    ensure_db()
    host = "127.0.0.1"
    port = 8765
    httpd = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Guardian Edge Agent running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
