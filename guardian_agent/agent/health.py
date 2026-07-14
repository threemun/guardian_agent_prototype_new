from __future__ import annotations

import datetime as dt
from statistics import mean
from typing import Any

from .db import dumps, now_iso, row_to_dict, rows_to_dicts, today_str


RISK_ORDER = {"normal": 0, "attention": 1, "abnormal": 2, "high_risk": 3}


class HealthAgent:
    """Daily data recorder and report generator."""

    def __init__(self, conn):
        self.conn = conn

    def record_vitals(self, elder_id: str, data: dict[str, Any]) -> dict[str, Any]:
        measured_at = data.get("measured_at") or now_iso()
        self.conn.execute(
            """
            INSERT INTO vitals
            (elder_id, measured_at, temperature, heart_rate, systolic_bp, diastolic_bp,
             fasting_glucose, blood_oxygen, sleep_hours, sleep_quality, steps, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                elder_id,
                measured_at,
                data.get("temperature"),
                data.get("heart_rate"),
                data.get("systolic_bp"),
                data.get("diastolic_bp"),
                data.get("fasting_glucose"),
                data.get("blood_oxygen"),
                data.get("sleep_hours"),
                data.get("sleep_quality"),
                data.get("steps"),
                data.get("note"),
            ),
        )
        self.conn.commit()
        return row_to_dict(self.conn.execute("SELECT * FROM vitals ORDER BY id DESC LIMIT 1").fetchone())

    def record_mock_abnormal(self, elder_id: str = "E001") -> dict[str, Any]:
        self.record_vitals(
            elder_id,
            {
                "temperature": 36.8,
                "heart_rate": 104,
                "systolic_bp": 156,
                "diastolic_bp": 94,
                "fasting_glucose": 7.6,
                "blood_oxygen": 96,
                "sleep_hours": 4.8,
                "sleep_quality": "偏浅",
                "steps": 1840,
                "note": "模拟健康异常数据",
            },
        )
        return self.generate_daily_report(elder_id)

    def generate_daily_report(self, elder_id: str = "E001", report_date: str | None = None) -> dict[str, Any]:
        report_date = report_date or today_str()
        elder = self._elder(elder_id)
        rows = self.conn.execute(
            """
            SELECT * FROM vitals
            WHERE elder_id = ? AND substr(measured_at, 1, 10) = ?
            ORDER BY measured_at DESC
            """,
            (elder_id, report_date),
        ).fetchall()
        if not rows:
            latest = self.conn.execute(
                "SELECT * FROM vitals WHERE elder_id = ? ORDER BY measured_at DESC LIMIT 1",
                (elder_id,),
            ).fetchone()
            rows = [latest] if latest else []
        vitals = [row_to_dict(row) for row in rows if row]
        latest_vital = vitals[0] if vitals else {}
        abnormal_items = self._analyze_vital(latest_vital)
        trend_findings = self._trend_findings(elder_id, report_date)
        risk_level = self._risk_from_items(abnormal_items)

        title = {
            "normal": "今日状态平稳",
            "attention": "今日健康需留意",
            "abnormal": "今日存在异常",
            "high_risk": "今日需及时确认",
        }[risk_level]

        summary = self._daily_summary(elder["name"], risk_level, abnormal_items, trend_findings)
        suggestions = self._suggestions(risk_level, abnormal_items)
        content = {
            "elder": {"id": elder["id"], "name": elder["name"], "age": elder["age"], "room": elder["room"]},
            "metrics": latest_vital,
            "abnormal_items": abnormal_items,
            "trend_findings": trend_findings,
            "suggestions": suggestions,
            "family_copy": summary,
            "data_quality": "good" if vitals else "partial",
            "disclaimer": "本报告仅用于日常健康管理参考，不能替代医生诊断。",
        }
        return self._save_report(elder_id, "daily", report_date, report_date, risk_level, title, summary, content)

    def generate_weekly_report(self, elder_id: str = "E001", week_end: str | None = None) -> dict[str, Any]:
        week_end_date = dt.date.fromisoformat(week_end or today_str())
        week_start_date = week_end_date - dt.timedelta(days=6)
        elder = self._elder(elder_id)
        rows = self.conn.execute(
            """
            SELECT * FROM vitals
            WHERE elder_id = ? AND substr(measured_at, 1, 10) BETWEEN ? AND ?
            ORDER BY measured_at ASC
            """,
            (elder_id, week_start_date.isoformat(), week_end_date.isoformat()),
        ).fetchall()
        vitals = [row_to_dict(row) for row in rows]
        abnormal_days = 0
        all_items: list[dict[str, Any]] = []
        for vital in vitals:
            items = self._analyze_vital(vital)
            if items:
                abnormal_days += 1
                all_items.extend(items)

        risk_level = "normal"
        if abnormal_days >= 4:
            risk_level = "abnormal"
        elif abnormal_days >= 2:
            risk_level = "attention"
        if any(item["severity"] == "high" for item in all_items):
            risk_level = "high_risk"

        avg_sleep = self._avg(vitals, "sleep_hours")
        avg_sys = self._avg(vitals, "systolic_bp")
        avg_dia = self._avg(vitals, "diastolic_bp")
        avg_glucose = self._avg(vitals, "fasting_glucose")
        key_findings = [
            f"本周共记录 {len(vitals)} 天健康数据，其中 {abnormal_days} 天存在需关注指标。",
            f"平均睡眠约 {avg_sleep:.1f} 小时。" if avg_sleep else "睡眠数据不足，建议保持每日记录。",
            f"平均血压约 {avg_sys:.0f}/{avg_dia:.0f} mmHg。" if avg_sys and avg_dia else "血压数据不足。",
            f"平均空腹血糖约 {avg_glucose:.1f} mmol/L。" if avg_glucose else "血糖数据不足。",
        ]
        suggestions = [
            "保持固定时间测量血压、血糖和睡眠数据。",
            "如果血压或血糖连续偏高，建议联系护理人员复核测量方式。",
            "子女端可重点关注夜间睡眠和起夜事件是否增多。",
        ]
        if risk_level in {"abnormal", "high_risk"}:
            suggestions.append("如伴随头晕、胸闷、明显乏力等不适，请及时咨询医生。")

        title = "本周健康周报"
        summary = f"{elder['name']}本周整体为{self._risk_cn(risk_level)}，主要关注睡眠、血压和血糖趋势。"
        content = {
            "elder": {"id": elder["id"], "name": elder["name"], "age": elder["age"], "room": elder["room"]},
            "week_range": f"{week_start_date.isoformat()} 至 {week_end_date.isoformat()}",
            "key_findings": key_findings,
            "main_risks": self._top_risks(all_items),
            "suggestions": suggestions,
            "averages": {
                "sleep_hours": round(avg_sleep, 1) if avg_sleep else None,
                "systolic_bp": round(avg_sys) if avg_sys else None,
                "diastolic_bp": round(avg_dia) if avg_dia else None,
                "fasting_glucose": round(avg_glucose, 1) if avg_glucose else None,
            },
            "data_quality": "good" if len(vitals) >= 6 else "partial",
            "disclaimer": "本报告仅用于日常健康管理参考，不能替代医生诊断。",
        }
        return self._save_report(
            elder_id,
            "weekly",
            week_start_date.isoformat(),
            week_end_date.isoformat(),
            risk_level,
            title,
            summary,
            content,
        )

    def latest_report(self, elder_id: str, report_type: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM reports
            WHERE elder_id = ? AND report_type = ?
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (elder_id, report_type),
        ).fetchone()
        return row_to_dict(row)

    def latest_vitals(self, elder_id: str, limit: int = 7) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT v.*, e.name AS elder_name, e.room AS elder_room
            FROM vitals v
            JOIN elders e ON e.id = v.elder_id
            WHERE v.elder_id = ?
            ORDER BY v.measured_at DESC
            LIMIT ?
            """,
            (elder_id, limit),
        ).fetchall()
        return rows_to_dicts(rows)

    def _analyze_vital(self, vital: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not vital:
            return items

        temp = vital.get("temperature")
        if temp is not None and temp >= 37.3:
            items.append(self._item("temperature", "体温", f"{temp:.1f} 摄氏度", "体温高于日常参考范围。", "medium" if temp < 38.5 else "high"))

        hr = vital.get("heart_rate")
        if hr is not None and (hr < 50 or hr > 100):
            severity = "high" if hr < 45 or hr > 120 else "medium"
            items.append(self._item("heart_rate", "心率", f"{hr} 次/分", "心率偏离日常参考范围。", severity))

        sys_bp = vital.get("systolic_bp")
        dia_bp = vital.get("diastolic_bp")
        if sys_bp is not None and dia_bp is not None and (sys_bp >= 140 or dia_bp >= 90):
            severity = "high" if sys_bp >= 180 or dia_bp >= 110 else "medium"
            items.append(self._item("blood_pressure", "血压", f"{sys_bp}/{dia_bp} mmHg", "血压偏高，建议复测并关注不适。", severity))

        glucose = vital.get("fasting_glucose")
        if glucose is not None and glucose >= 7.0:
            severity = "high" if glucose >= 11.1 else "medium"
            items.append(self._item("fasting_glucose", "空腹血糖", f"{glucose:.1f} mmol/L", "血糖高于日常参考范围。", severity))

        spo2 = vital.get("blood_oxygen")
        if spo2 is not None and spo2 < 95:
            severity = "high" if spo2 < 93 else "medium"
            items.append(self._item("blood_oxygen", "血氧", f"{spo2}%", "血氧偏低，建议复测确认。", severity))

        sleep = vital.get("sleep_hours")
        if sleep is not None and sleep < 5.5:
            items.append(self._item("sleep", "睡眠", f"{sleep:.1f} 小时", "睡眠时长偏短，可能影响白天状态。", "low"))
        return items

    def _item(self, key: str, label: str, value: str, analysis: str, severity: str) -> dict[str, Any]:
        return {"item": key, "display_name": label, "value": value, "analysis": analysis, "severity": severity}

    def _trend_findings(self, elder_id: str, report_date: str) -> list[str]:
        end = dt.date.fromisoformat(report_date)
        start = end - dt.timedelta(days=6)
        prev_start = start - dt.timedelta(days=7)
        prev_end = start - dt.timedelta(days=1)
        recent = self._vitals_between(elder_id, start, end)
        previous = self._vitals_between(elder_id, prev_start, prev_end)
        findings: list[str] = []
        recent_sleep = self._avg(recent, "sleep_hours")
        prev_sleep = self._avg(previous, "sleep_hours")
        if recent_sleep and prev_sleep and recent_sleep < prev_sleep - 0.7:
            findings.append(f"近 7 天平均睡眠较前一周下降约 {prev_sleep - recent_sleep:.1f} 小时。")
        recent_bp = self._avg(recent, "systolic_bp")
        prev_bp = self._avg(previous, "systolic_bp")
        if recent_bp and prev_bp and recent_bp > prev_bp + 8:
            findings.append("近 7 天收缩压较前一周有所升高。")
        recent_glucose = self._avg(recent, "fasting_glucose")
        prev_glucose = self._avg(previous, "fasting_glucose")
        if recent_glucose and prev_glucose and recent_glucose > prev_glucose + 0.6:
            findings.append("近 7 天空腹血糖较前一周偏高。")
        return findings or ["近期数据整体变化不大，建议继续保持记录。"]

    def _vitals_between(self, elder_id: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM vitals
            WHERE elder_id = ? AND substr(measured_at, 1, 10) BETWEEN ? AND ?
            ORDER BY measured_at ASC
            """,
            (elder_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return rows_to_dicts(rows)

    def _risk_from_items(self, items: list[dict[str, Any]]) -> str:
        if any(item["severity"] == "high" for item in items):
            return "high_risk"
        if any(item["severity"] == "medium" for item in items):
            return "attention"
        if items:
            return "attention"
        return "normal"

    def _daily_summary(self, name: str, risk_level: str, items: list[dict[str, Any]], trends: list[str]) -> str:
        if not items:
            return f"{name}今日体征整体平稳，未发现明显异常。{trends[0]}"
        names = "、".join(item["display_name"] for item in items[:3])
        return f"{name}今日主要需关注{name and ''}{names}，建议家属留意状态变化并按需复测。"

    def _suggestions(self, risk_level: str, items: list[dict[str, Any]]) -> list[str]:
        suggestions = ["保持今日体征数据记录，晚间可再次查看睡眠和活动情况。"]
        keys = {item["item"] for item in items}
        if "blood_pressure" in keys:
            suggestions.append("建议在安静休息后再次测量血压，并记录测量时间。")
        if "fasting_glucose" in keys:
            suggestions.append("关注今日饮食和血糖记录，如连续偏高建议联系护理人员复核。")
        if "sleep" in keys:
            suggestions.append("今晚尽量保持安静环境，观察是否频繁起夜或睡眠变浅。")
        if "heart_rate" in keys:
            suggestions.append("如伴随胸闷、头晕或明显不适，请及时联系医生。")
        if risk_level == "high_risk":
            suggestions.append("建议子女或护理人员尽快确认老人当前状态。")
        while len(suggestions) < 3:
            suggestions.append("如老人反馈不适，请联系护理人员进一步确认。")
        return suggestions[:5]

    def _risk_cn(self, risk_level: str) -> str:
        return {"normal": "平稳", "attention": "需关注", "abnormal": "存在异常", "high_risk": "高风险"}[risk_level]

    def _top_risks(self, items: list[dict[str, Any]]) -> list[str]:
        seen: list[str] = []
        for item in items:
            label = item["display_name"]
            if label not in seen:
                seen.append(label)
        return seen[:5]

    def _avg(self, rows: list[dict[str, Any]], key: str) -> float | None:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        return mean(values) if values else None

    def _elder(self, elder_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM elders WHERE id = ?", (elder_id,)).fetchone()
        elder = row_to_dict(row)
        if elder is None:
            raise ValueError(f"elder not found: {elder_id}")
        return elder

    def _save_report(
        self,
        elder_id: str,
        report_type: str,
        period_start: str,
        period_end: str,
        risk_level: str,
        title: str,
        summary: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            INSERT INTO reports
            (elder_id, report_type, period_start, period_end, risk_level, title, summary, content_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (elder_id, report_type, period_start, period_end, risk_level, title, summary, dumps(content), now_iso()),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 1").fetchone()
        return row_to_dict(row)
