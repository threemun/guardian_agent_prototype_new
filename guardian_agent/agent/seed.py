from __future__ import annotations

import datetime as dt

from .db import dumps, init_db, now_iso, today_str
from .health import HealthAgent
from .memory import MOCK_CALLS, MemoryAgent, ensure_sample_audio_files
from .night import NightCareAgent


ELDERS = [
    (
        "E001",
        "王爷爷",
        82,
        "男",
        "A 区 301",
        "重点照护",
        "王女士",
        "138****5601",
        "27316001",
        ["高血压", "糖代谢异常"],
        {"heart_rate": 76, "systolic_bp": 132, "diastolic_bp": 82, "sleep_hours": 6.4},
    ),
    (
        "E002",
        "张爷爷",
        79,
        "男",
        "A 区 302",
        "普通照护",
        "张先生",
        "139****2108",
        "27316002",
        ["骨质疏松"],
        {"heart_rate": 72, "systolic_bp": 128, "diastolic_bp": 80, "sleep_hours": 6.8},
    ),
    (
        "E003",
        "李奶奶",
        84,
        "女",
        "B 区 106",
        "重点照护",
        "李女士",
        "136****8890",
        "27316003",
        ["冠心病风险", "高血压"],
        {"heart_rate": 78, "systolic_bp": 136, "diastolic_bp": 84, "sleep_hours": 6.0},
    ),
]


def seed_demo_data(reset: bool = True) -> None:
    from .db import get_conn

    clear_existing = False
    try:
        init_db(reset=reset)
    except PermissionError:
        if not reset:
            raise
        init_db(reset=False)
        clear_existing = True

    with get_conn() as conn:
        if clear_existing:
            clear_demo_tables(conn)
        now = now_iso()
        for elder in ELDERS:
            conn.execute(
                """
                INSERT INTO elders
                (id, name, age, gender, room, care_level, primary_contact, phone_mask, device_host,
                 chronic_conditions_json, baseline_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*elder[:9], dumps(elder[9]), dumps(elder[10]), now),
            )

        devices = []
        for index, elder in enumerate(ELDERS, start=1):
            elder_id = elder[0]
            devices.extend(
                [
                    (f"dev_sleep_{index:03d}", elder_id, "sleep_band", "卧室", "online"),
                    (f"dev_radar_{index:03d}", elder_id, "radar", "卧室", "online"),
                    (f"dev_sos_{index:03d}", elder_id, "sos_button", "客厅", "online"),
                    (f"dev_vital_{index:03d}", elder_id, "health_station", "床旁", "online"),
                ]
            )
        for device in devices:
            conn.execute(
                "INSERT INTO devices (id, elder_id, kind, location, status, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                (*device, now),
            )

        base_date = dt.date.fromisoformat(today_str())
        health_agent = HealthAgent(conn)
        health_profiles = {
            "E001": {"sleep": 6.7, "sys": 134, "dia": 82, "glucose": 6.2, "hr": 76, "steps": 2100},
            "E002": {"sleep": 7.1, "sys": 126, "dia": 78, "glucose": 5.8, "hr": 72, "steps": 2600},
            "E003": {"sleep": 6.1, "sys": 138, "dia": 84, "glucose": 6.0, "hr": 78, "steps": 1900},
        }
        for elder_id, profile in health_profiles.items():
            for i in range(13, -1, -1):
                day = base_date - dt.timedelta(days=i)
                measured_at = f"{day.isoformat()}T08:10:00"
                recent_pressure = max(0, 6 - i)
                health_agent.record_vitals(
                    elder_id,
                    {
                        "measured_at": measured_at,
                        "temperature": 36.4 + (i % 3) * 0.1,
                        "heart_rate": profile["hr"] + (i % 4),
                        "systolic_bp": profile["sys"] + (recent_pressure if elder_id != "E002" else i % 3),
                        "diastolic_bp": profile["dia"] + (i % 4),
                        "fasting_glucose": round(profile["glucose"] + recent_pressure * 0.08, 1),
                        "blood_oxygen": 96 + (i % 3),
                        "sleep_hours": round(profile["sleep"] - recent_pressure * 0.12, 1),
                        "sleep_quality": "正常" if i > 3 else "一般",
                        "steps": profile["steps"] + i * 45,
                        "note": "模拟日常记录",
                    },
                )

        evening_records = {
            "E001": {
                "heart_rate": 104,
                "systolic_bp": 156,
                "diastolic_bp": 94,
                "fasting_glucose": 7.6,
                "sleep_hours": 4.8,
                "sleep_quality": "偏浅",
                "steps": 1840,
                "note": "晚间补充测量，血压和睡眠需关注",
            },
            "E002": {
                "heart_rate": 78,
                "systolic_bp": 132,
                "diastolic_bp": 82,
                "fasting_glucose": 6.1,
                "sleep_hours": 6.9,
                "sleep_quality": "正常",
                "steps": 2860,
                "note": "晚间补充测量，整体平稳",
            },
            "E003": {
                "heart_rate": 92,
                "systolic_bp": 148,
                "diastolic_bp": 90,
                "fasting_glucose": 6.8,
                "sleep_hours": 5.4,
                "sleep_quality": "一般",
                "steps": 1760,
                "note": "晚间补充测量，血压和睡眠需留意",
            },
        }
        for elder_id, data in evening_records.items():
            health_agent.record_vitals(
                elder_id,
                {
                    "measured_at": f"{base_date.isoformat()}T20:30:00",
                    "temperature": 36.7,
                    "blood_oxygen": 96,
                    **data,
                },
            )
            health_agent.generate_daily_report(elder_id, base_date.isoformat())
            health_agent.generate_weekly_report(elder_id, base_date.isoformat())

        night_agent = NightCareAgent(conn)
        night_agent.trigger_possible_leave_bed("E001", scenario="critical", location="卧室")
        night_agent.trigger_possible_leave_bed("E002", scenario="standard", location="卧室")
        night_agent.trigger_sos("E003", location="客厅")

        ensure_sample_audio_files()
        memory_agent = MemoryAgent(conn)
        for item in MOCK_CALLS:
            memory_agent.create_mock_memory(item["key"], item["elder_id"])
        conn.commit()


def clear_demo_tables(conn) -> None:
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    tables = [
        "notifications",
        "conversation_turns",
        "decisions",
        "events",
        "raw_messages",
        "reports",
        "vitals",
        "memory_segments",
        "call_recordings",
        "devices",
        "elders",
    ]
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in tables:
        if table in existing:
            conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
