from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "guardian_agent.sqlite3"


JSON_COLUMNS = {
    "chronic_conditions_json",
    "baseline_json",
    "payload_json",
    "evidence_json",
    "tools_json",
    "actions_json",
    "result_json",
    "content_json",
    "metrics_json",
    "metadata_json",
    "people_json",
    "keywords_json",
    "entities_json",
}


class GuardianConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def today_str() -> str:
    return dt.date.today().isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, factory=GuardianConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in list(data):
        if key in JSON_COLUMNS:
            data[key[:-5] if key.endswith("_json") else key] = loads(data[key], [] if key.endswith("_json") else {})
            data.pop(key, None)
    return data


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS elders (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                room TEXT NOT NULL,
                care_level TEXT NOT NULL,
                primary_contact TEXT NOT NULL,
                phone_mask TEXT NOT NULL,
                device_host TEXT NOT NULL,
                chronic_conditions_json TEXT NOT NULL,
                baseline_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                elder_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS raw_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                topic TEXT NOT NULL,
                elder_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                processed_status TEXT NOT NULL,
                result_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                elder_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                location TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                description TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                tools_json TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                step_order INTEGER NOT NULL,
                step_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                tool_name TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS conversation_turns (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                elder_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id),
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                report_id INTEGER,
                target TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS vitals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elder_id TEXT NOT NULL,
                measured_at TEXT NOT NULL,
                temperature REAL,
                heart_rate INTEGER,
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                fasting_glucose REAL,
                blood_oxygen INTEGER,
                sleep_hours REAL,
                sleep_quality TEXT,
                steps INTEGER,
                note TEXT,
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                elder_id TEXT NOT NULL,
                report_type TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                content_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS call_recordings (
                id TEXT PRIMARY KEY,
                elder_id TEXT NOT NULL,
                family_member TEXT NOT NULL,
                call_started_at TEXT NOT NULL,
                audio_uri TEXT NOT NULL,
                audio_duration_seconds INTEGER NOT NULL,
                transcript TEXT NOT NULL,
                stt_provider TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );

            CREATE TABLE IF NOT EXISTS memory_segments (
                id TEXT PRIMARY KEY,
                recording_id TEXT NOT NULL,
                elder_id TEXT NOT NULL,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                memory_time_text TEXT NOT NULL,
                memory_date TEXT NOT NULL,
                people_json TEXT NOT NULL,
                emotion TEXT NOT NULL,
                sentiment_score REAL NOT NULL,
                event_summary TEXT NOT NULL,
                lyric_text TEXT NOT NULL,
                source_text TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                entities_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (recording_id) REFERENCES call_recordings(id),
                FOREIGN KEY (elder_id) REFERENCES elders(id)
            );
            """
        )
        ensure_schema(conn)


def ensure_schema(conn: sqlite3.Connection) -> None:
    raw_message_columns = {row[1] for row in conn.execute("PRAGMA table_info(raw_messages)").fetchall()}
    if "result_json" not in raw_message_columns:
        conn.execute("ALTER TABLE raw_messages ADD COLUMN result_json TEXT NOT NULL DEFAULT '{}'")

    """Small forward migrations for local prototype databases."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(memory_segments)").fetchall()}
    if "memory_date" not in columns:
        conn.execute("ALTER TABLE memory_segments ADD COLUMN memory_date TEXT NOT NULL DEFAULT ''")
