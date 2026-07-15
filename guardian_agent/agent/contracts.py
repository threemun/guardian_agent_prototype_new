from __future__ import annotations

from enum import Enum


CONTRACT_VERSION = "1.0"


class GuardianEventType(str, Enum):
    """Events accepted by the GuardianMessage 1.0 boundary."""

    LEAVE_BED = "LEAVE_BED"
    RETURN_TO_BED = "RETURN_TO_BED"
    PRESENCE_CHANGED = "PRESENCE_CHANGED"
    FALL_DETECTED = "FALL_DETECTED"
    NO_RESPONSE_TIMEOUT = "NO_RESPONSE_TIMEOUT"
    VOICE_TRANSCRIPT = "VOICE_TRANSCRIPT"
    VITALS_RECORDED = "VITALS_RECORDED"
    DAILY_REPORT_REQUESTED = "DAILY_REPORT_REQUESTED"
    WEEKLY_REPORT_REQUESTED = "WEEKLY_REPORT_REQUESTED"


class NightEventStatus(str, Enum):
    """Possible states of one night-care event."""

    NEW = "NEW"
    WAITING_ELDER_CONFIRM = "WAITING_ELDER_CONFIRM"
    CLARIFYING = "CLARIFYING"
    MONITORING_RETURN = "MONITORING_RETURN"
    WAITING_FAMILY_CONFIRM = "WAITING_FAMILY_CONFIRM"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


class ElderIntent(str, Enum):
    """Normalized meanings supported by the first night-turn contract."""

    OK = "ok"
    BATHROOM = "bathroom"
    DRINK = "drink"
    MEDICATION = "medication"
    DIZZY = "dizzy"
    PAIN = "pain"
    FALL = "fall"
    NEED_HELP = "need_help"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def enum_values(enum_type: type[Enum]) -> list[str]:
    return [item.value for item in enum_type]

