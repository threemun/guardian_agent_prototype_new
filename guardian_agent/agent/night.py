from __future__ import annotations

import uuid
from typing import Any

from .db import dumps, loads, now_iso, row_to_dict, rows_to_dicts


STATUS_LABELS = {
    "WAITING_ELDER_CONFIRM": "等待老人确认",
    "WAITING_FAMILY_CONFIRM": "等待子女确认",
    "MONITORING_RETURN": "观察返床",
    "ESCALATED": "已升级",
    "CLOSED": "已关闭",
}

RISK_LABELS = {
    "INFO": "记录",
    "WARNING": "需关注",
    "CRITICAL": "紧急",
}


class NightCareAgent:
    """Fixed-flow night-care agent for the early SQLite prototype."""

    def __init__(self, conn):
        self.conn = conn

    def ingest_sensor_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        message_id = payload.get("message_id") or f"msg_{uuid.uuid4().hex}"
        elder_id = payload.get("elder_id", "E001")
        topic = payload.get("topic", "edge.sleep.event")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO raw_messages
            (message_id, source, topic, elder_id, payload_json, received_at, processed_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                payload.get("source_system", "mock_edge"),
                topic,
                elder_id,
                dumps(payload),
                now_iso(),
                "accepted",
            ),
        )
        event_type = payload.get("event_type", "POSSIBLE_LEAVE_BED")
        if event_type == "SOS_BUTTON":
            return self.trigger_sos(elder_id=elder_id, location=payload.get("location", "客厅"))
        return self.trigger_possible_leave_bed(
            elder_id=elder_id,
            scenario=payload.get("scenario", "standard"),
            signals=payload.get("signals", {}),
            location=payload.get("location", "卧室"),
        )

    def trigger_possible_leave_bed(
        self,
        elder_id: str = "E001",
        scenario: str = "standard",
        signals: dict[str, Any] | None = None,
        location: str = "卧室",
    ) -> dict[str, Any]:
        elder = self._elder(elder_id)
        signals = signals or {
            "sleep_band_no_body_seconds": 320,
            "radar_movement": True,
            "night_time": True,
            "ambient_light": "low",
        }
        no_body_seconds = int(signals.get("sleep_band_no_body_seconds", 0))
        radar_movement = bool(signals.get("radar_movement", False))
        night_time = bool(signals.get("night_time", True))

        risk_level = "WARNING"
        status = "WAITING_ELDER_CONFIRM"
        confidence = 0.72
        description = "凌晨检测到床上无人，雷达检测卧室活动，已开启夜灯并询问老人意图。"
        actions = ["open_night_light", "ask_elder_intent", "wait_elder_feedback"]

        if scenario in {"no_response", "critical"} or (night_time and no_body_seconds >= 600 and not radar_movement):
            risk_level = "CRITICAL"
            status = "WAITING_FAMILY_CONFIRM"
            confidence = 0.86
            description = "夜间离床超过阈值且老人未及时反馈，已通知子女并标记为紧急关注。"
            actions = ["open_night_light", "ask_elder_intent", "notify_family", "create_case"]

        event = self._create_event(
            elder_id=elder_id,
            event_type="POSSIBLE_LEAVE_BED",
            title=f"{elder['name']} · 疑似夜间离床",
            status=status,
            risk_level=risk_level,
            location=location,
            source="sleep_band + radar",
            confidence=confidence,
            description=description,
            evidence=[
                f"sleep_band_no_body_{no_body_seconds}s",
                "night_time" if night_time else "day_time",
                "radar_movement" if radar_movement else "radar_no_movement",
            ],
            tools=["SceneTool", "ElderAskTool", "NotifyTool", "CaseTool"],
            actions=actions,
        )

        self._add_step(event["id"], "observe", "接收 POSSIBLE_LEAVE_BED", "设备事件抽象层生成疑似离床事件。")
        self._add_step(
            event["id"],
            "guardrail",
            "规则护栏判断",
            "夜间离床超过阈值，结合雷达活动与反馈状态确定风险等级。",
        )
        self._add_step(event["id"], "tool", "打开夜灯", "调用智能场景降低环境风险。", "SceneTool")
        self._add_step(event["id"], "tool", "询问老人意图", "老人端展示确认按钮，等待反馈。", "ElderAskTool")
        if risk_level == "CRITICAL":
            self._notify_family(event["id"], elder["primary_contact"], "起夜事件需确认", description)
            self._add_step(event["id"], "tool", "通知子女端", "已推送紧急确认卡片到子女端 App。", "NotifyTool")
            self._add_step(event["id"], "tool", "创建事件工单", "已生成待确认事件，保留全链路证据。", "CaseTool")
        self.conn.commit()
        return self.get_event(event["id"])

    def trigger_sos(self, elder_id: str = "E003", location: str = "客厅") -> dict[str, Any]:
        elder = self._elder(elder_id)
        event = self._create_event(
            elder_id=elder_id,
            event_type="SOS_BUTTON",
            title=f"{elder['name']} · SOS 按钮报警",
            status="WAITING_FAMILY_CONFIRM",
            risk_level="CRITICAL",
            location=location,
            source="sos_button",
            confidence=0.96,
            description="SOS 按钮触发，已直接通知子女并建议发起视频确认。",
            evidence=["sos_button_pressed", "device_online", "manual_trigger"],
            tools=["NotifyTool", "VideoCallTool", "CaseTool"],
            actions=["notify_family", "suggest_video_call", "create_case"],
        )
        self._add_step(event["id"], "observe", "接收 SOS_BUTTON", "老人端 SOS 按钮被触发。")
        self._add_step(event["id"], "tool", "通知子女端", "已推送 SOS 紧急提醒。", "NotifyTool")
        self._add_step(event["id"], "tool", "建议视频通话", "子女端展示一键视频确认入口。", "VideoCallTool")
        self._notify_family(event["id"], elder["primary_contact"], "SOS 紧急提醒", event["description"])
        self.conn.commit()
        return self.get_event(event["id"])

    def trigger_health_abnormal(self, elder_id: str = "E001", report: dict[str, Any] | None = None) -> dict[str, Any]:
        elder = self._elder(elder_id)
        report = report or {}
        content = report.get("content") or {}
        abnormal_items = content.get("abnormal_items") or []
        risk = report.get("risk_level") or "attention"
        risk_level = "CRITICAL" if risk == "high_risk" else "WARNING"
        status = "WAITING_FAMILY_CONFIRM" if risk_level == "CRITICAL" else "WAITING_ELDER_CONFIRM"
        evidence = [item.get("item", "vital_abnormal") for item in abnormal_items] or ["daily_vitals_abnormal"]
        item_names = "、".join(item.get("display_name", "健康指标") for item in abnormal_items[:3]) or "健康指标"
        description = f"日常数据检测到{item_names}需要关注，已生成健康日报并等待老人或子女确认。"

        event = self._create_event(
            elder_id=elder_id,
            event_type="HEALTH_ABNORMAL",
            title=f"{elder['name']} · 健康指标异常",
            status=status,
            risk_level=risk_level,
            location=elder.get("room", "居家"),
            source="vitals + health_report",
            confidence=0.78 if risk_level == "WARNING" else 0.88,
            description=description,
            evidence=evidence,
            tools=["HealthReportTool", "NotifyTool", "CaseTool"],
            actions=["generate_daily_report", "ask_elder_status", "notify_family_if_needed"],
        )
        self._add_step(event["id"], "observe", "接收健康异常数据", "体征记录进入 Agent，发现部分指标超出日常关注阈值。")
        self._add_step(event["id"], "guardrail", "健康风险分级", f"根据日报风险等级 {risk}，将事件标记为 {risk_level}。")
        self._add_step(event["id"], "tool", "生成健康日报", "已汇总最新体温、心率、血压、血糖、血氧和睡眠数据。", "HealthReportTool")
        if risk_level == "CRITICAL":
            self._add_step(event["id"], "tool", "通知子女确认", "风险较高，向子女端推送健康异常确认卡片。", "NotifyTool")
            self._notify_family(event["id"], elder["primary_contact"], "健康异常需确认", description)
        else:
            self._add_step(event["id"], "plan", "等待老人反馈", "优先请老人确认当前感受，如出现不适再升级通知子女。")
        self.conn.commit()
        return self.get_event(event["id"])

    def apply_feedback(
        self,
        event_id: str,
        feedback_type: str,
        original_text: str = "",
        source: str = "elder_app",
    ) -> dict[str, Any]:
        event = self.get_event(event_id)
        if not event:
            raise ValueError("event not found")

        feedback_map = {
            "ok": ("老人反馈：我没事", "老人确认当前无不适，事件可关闭。"),
            "bathroom": ("老人反馈：去洗手间", "记录起夜原因，进入返床观察。"),
            "drink": ("老人反馈：喝水", "记录起夜原因，短时观察即可。"),
            "dizzy": ("老人反馈：头晕", "老人反馈头晕，升级为紧急关注。"),
            "need_help": ("老人反馈：需要帮助", "老人主动请求帮助，通知子女与护理人员。"),
        }
        title, desc = feedback_map.get(feedback_type, ("老人反馈", "已记录老人端反馈。"))
        self._add_step(
            event_id,
            "feedback",
            title,
            desc,
            "ElderAskTool",
            {"feedback_type": feedback_type, "original_text": original_text, "source": source},
        )

        if feedback_type == "ok":
            self._update_event(event_id, status="CLOSED", risk_level="INFO", closed=True, description="老人已确认无事，事件关闭并归档。")
        elif feedback_type in {"bathroom", "drink"}:
            self._update_event(event_id, status="MONITORING_RETURN", risk_level="WARNING", description=desc)
            self._add_step(event_id, "plan", "设置返床观察", "15 分钟内持续关注是否返床。", "CaseTool")
        elif feedback_type in {"dizzy", "need_help"}:
            self._update_event(event_id, status="WAITING_FAMILY_CONFIRM", risk_level="CRITICAL", description=desc)
            self._add_step(event_id, "tool", "通知子女端", "已升级为紧急确认。", "NotifyTool")
            self._notify_family(event_id, event["elder"]["primary_contact"], "老人需要关注", desc)
        self.conn.commit()
        return self.get_event(event_id)

    def record_device_action(
        self,
        event_id: str,
        action: str,
        success: bool,
        detail: str = "",
        source: str = "tuya_agent",
    ) -> dict[str, Any]:
        event = self.get_event(event_id)
        if not event:
            raise ValueError("event not found")
        title = "设备动作完成" if success else "设备动作失败"
        desc = f"{source} 执行 {action}：{detail or ('success' if success else 'failed')}"
        self._add_step(
            event_id,
            "tool",
            title,
            desc,
            "TuyaDeviceTool",
            {"action": action, "success": success, "detail": detail, "source": source},
        )
        self.conn.commit()
        return self.get_event(event_id)

    def simulate_timeout(self, event_id: str) -> dict[str, Any]:
        event = self.get_event(event_id)
        if not event:
            raise ValueError("event not found")
        self._add_step(event_id, "guardrail", "模拟无响应超时", "老人端长时间未反馈，进入升级流程。")
        self._update_event(
            event_id,
            status="WAITING_FAMILY_CONFIRM",
            risk_level="CRITICAL",
            description="老人端无响应超时，已通知子女确认。",
        )
        self._add_step(event_id, "tool", "通知子女端", "已推送无响应超时提醒。", "NotifyTool")
        self._notify_family(event_id, event["elder"]["primary_contact"], "无响应超时", "老人端未按时反馈，请尽快确认。")
        self.conn.commit()
        return self.get_event(event_id)

    def close_event(self, event_id: str) -> dict[str, Any]:
        event = self.get_event(event_id)
        if not event:
            raise ValueError("event not found")
        self._add_step(event_id, "close", "关闭事件", "事件已由演示控制台关闭并归档。", "CaseTool")
        self._update_event(event_id, status="CLOSED", closed=True, description="事件已关闭归档。")
        self.conn.commit()
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        event = row_to_dict(self.conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        if not event:
            return None
        event["elder"] = self._elder(event["elder_id"])
        event["status_label"] = STATUS_LABELS.get(event["status"], event["status"])
        event["risk_label"] = RISK_LABELS.get(event["risk_level"], event["risk_level"])
        event["timeline"] = self.get_timeline(event_id)
        return event

    def get_timeline(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE event_id = ? ORDER BY step_order ASC, id ASC",
            (event_id,),
        ).fetchall()
        return rows_to_dicts(rows)

    def _elder(self, elder_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM elders WHERE id = ?", (elder_id,)).fetchone()
        elder = row_to_dict(row)
        if elder is None:
            raise ValueError(f"elder not found: {elder_id}")
        return elder

    def _create_event(
        self,
        elder_id: str,
        event_type: str,
        title: str,
        status: str,
        risk_level: str,
        location: str,
        source: str,
        confidence: float,
        description: str,
        evidence: list[str],
        tools: list[str],
        actions: list[str],
    ) -> dict[str, Any]:
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        created_at = now_iso()
        self.conn.execute(
            """
            INSERT INTO events
            (id, elder_id, type, title, status, risk_level, location, source, confidence, description,
             evidence_json, tools_json, actions_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                elder_id,
                event_type,
                title,
                status,
                risk_level,
                location,
                source,
                confidence,
                description,
                dumps(evidence),
                dumps(tools),
                dumps(actions),
                created_at,
                created_at,
            ),
        )
        return row_to_dict(self.conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())

    def _update_event(self, event_id: str, closed: bool = False, **fields: Any) -> None:
        allowed = {"status", "risk_level", "description"}
        assignments = []
        values = []
        for key, value in fields.items():
            if key in allowed:
                assignments.append(f"{key} = ?")
                values.append(value)
        assignments.append("updated_at = ?")
        values.append(now_iso())
        if closed:
            assignments.append("closed_at = ?")
            values.append(now_iso())
        values.append(event_id)
        self.conn.execute(f"UPDATE events SET {', '.join(assignments)} WHERE id = ?", values)

    def _add_step(
        self,
        event_id: str,
        step_type: str,
        title: str,
        description: str,
        tool_name: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        current = self.conn.execute("SELECT COALESCE(MAX(step_order), 0) FROM decisions WHERE event_id = ?", (event_id,)).fetchone()[0]
        self.conn.execute(
            """
            INSERT INTO decisions
            (event_id, step_order, step_type, title, description, tool_name, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, current + 1, step_type, title, description, tool_name, dumps(result or {}), now_iso()),
        )

    def _notify_family(self, event_id: str, target: str, title: str, message: str) -> None:
        self.conn.execute(
            """
            INSERT INTO notifications
            (event_id, target, title, message, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, target, title, message, "sent", now_iso()),
        )
