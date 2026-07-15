from __future__ import annotations

from typing import Any

from .night import NightCareAgent


DANGER_KEYWORDS = [
    "摔",
    "摔倒",
    "跌倒",
    "倒了",
    "倒了一下",
    "倒在",
    "起不来",
    "站不起来",
    "扶",
    "帮",
    "救",
    "胸闷",
    "胸口",
    "呼吸",
    "喘",
    "腿没劲",
    "站不稳",
    "走不稳",
    "疼",
]
DIZZY_KEYWORDS = ["头晕", "晕", "眩晕", "发昏"]
BATHROOM_KEYWORDS = ["厕所", "卫生间", "洗手间", "方便", "小便", "起夜", "解手", "解个手"]
DRINK_KEYWORDS = ["喝水", "口渴", "口干", "倒水", "水"]
MEDICATION_KEYWORDS = ["药", "吃药", "降压药", "找药"]
OK_KEYWORDS = ["没事", "不用管", "不用担心", "还好", "没关系", "马上回去"]


def classify_elder_reply(text: str) -> dict[str, Any]:
    original = (text or "").strip()
    normalized = original.replace(" ", "")
    if not normalized:
        return _intent("unknown", "unknown", 0.2, True, [], "未收到清晰回答。")

    symptoms: list[str] = []
    if _contains_any(normalized, DANGER_KEYWORDS):
        symptoms.append("high_risk_expression")
        return _intent("need_help", "need_help", 0.92, False, symptoms, "检测到求助、跌倒或明显不适表达。")
    if _contains_any(normalized, DIZZY_KEYWORDS):
        symptoms.append("dizzy")
        return _intent("dizzy", "dizzy", 0.9, False, symptoms, "检测到头晕相关表达。")
    if _contains_any(normalized, MEDICATION_KEYWORDS):
        return _intent("medication", "unknown", 0.72, True, [], "老人提到用药，需要进一步确认是否安全。")
    if _contains_any(normalized, BATHROOM_KEYWORDS):
        return _intent("bathroom", "bathroom", 0.88, False, symptoms, "检测到去洗手间相关表达。")
    if _contains_any(normalized, DRINK_KEYWORDS):
        return _intent("drink", "drink", 0.86, False, symptoms, "检测到喝水相关表达。")
    if _contains_any(normalized, OK_KEYWORDS):
        return _intent("ok", "ok", 0.82, False, symptoms, "检测到安全确认表达。")
    return _intent("unknown", "unknown", 0.42, True, symptoms, "回答不明确。")


def handle_night_turn(conn, payload: dict[str, Any]) -> dict[str, Any]:
    elder_id = str(payload.get("elder_id") or "E001")
    text = str(payload.get("text") or payload.get("transcript") or "").strip()
    source = str(payload.get("source") or "night_turn")
    session_id = str(payload.get("session_id") or "")
    agent = NightCareAgent(conn)
    event_id = str(payload.get("event_id") or "").strip() or _latest_open_event_id(conn, elder_id)
    classification = classify_elder_reply(text)
    event = agent.apply_feedback(
        event_id=event_id,
        feedback_type=classification["feedback_type"],
        original_text=text,
        source=source,
    )
    reply_text = _reply_text(classification["intent"], classification["requires_clarification"])
    tool_calls = ["get_active_event", "submit_elder_feedback"] if not payload.get("event_id") else ["submit_elder_feedback"]
    return {
        "intent": classification["intent"],
        "feedback_type": classification["feedback_type"],
        "confidence": classification["confidence"],
        "symptoms": classification["symptoms"],
        "requires_clarification": classification["requires_clarification"],
        "analysis": classification["analysis"],
        "elder_id": elder_id,
        "event_id": event_id,
        "session_id": session_id,
        "event_status": event["status"],
        "risk_level": event["risk_level"],
        "reply_text": reply_text,
        "tool_calls": tool_calls,
        "event": event,
    }


def _intent(
    intent: str,
    feedback_type: str,
    confidence: float,
    requires_clarification: bool,
    symptoms: list[str],
    analysis: str,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "feedback_type": feedback_type,
        "confidence": confidence,
        "requires_clarification": requires_clarification,
        "symptoms": symptoms,
        "analysis": analysis,
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _reply_text(intent: str, requires_clarification: bool) -> str:
    if requires_clarification:
        return "我没有听清楚，您是去洗手间、喝水，还是需要帮助？"
    replies = {
        "ok": "好的，已记录您当前安全，请慢慢回到床上。",
        "bathroom": "好的，已记录您去洗手间，我会继续关注您是否安全回床。",
        "drink": "好的，已记录您起来喝水，请注意脚下安全。",
        "dizzy": "我已记录您头晕，请您先坐稳不要走动，家人会收到提醒。",
        "need_help": "我已经发起帮助请求，请您保持安全姿势等待家人或护理人员确认。",
    }
    return replies.get(intent, "好的，我已记录。")


def _latest_open_event_id(conn, elder_id: str) -> str:
    row = conn.execute(
        """
        SELECT id FROM events
        WHERE elder_id = ? AND status != 'CLOSED'
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (elder_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"no active event found for elder_id: {elder_id}")
    return row["id"]
