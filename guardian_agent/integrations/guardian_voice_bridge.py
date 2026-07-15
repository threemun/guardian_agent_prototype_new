from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_AGENT_URL = "http://127.0.0.1:8765/api/v1/guardian/conversations/night-turn"
DEFAULT_VOICE_LAB_DIR = Path(os.getenv("VOICE_LAB_DIR", "") or r"C:\Users\Wu Ting\Desktop\物联网\agent开发\voice_lab")


def load_voice_service(voice_lab_dir: Path):
    voice_lab_file = voice_lab_dir / "voice_lab.py"
    if not voice_lab_file.exists():
        raise FileNotFoundError(
            f"未找到 voice_lab.py：{voice_lab_file}\n"
            "请先把 voice_lab 1.3.zip 解压成 voice_lab 目录，或用 --voice-lab-dir 指定目录。"
        )
    spec = importlib.util.spec_from_file_location("guardian_voice_lab", voice_lab_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 voice_lab.py：{voice_lab_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["guardian_voice_lab"] = module
    spec.loader.exec_module(module)
    return module.VoiceService()


def post_night_turn(
    agent_url: str,
    elder_id: str,
    text: str,
    event_id: str = "",
    session_id: str = "",
    source: str = "voice_lab",
) -> dict[str, Any]:
    payload = {
        "elder_id": elder_id,
        "event_id": event_id,
        "session_id": session_id,
        "text": text,
        "source": source,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        agent_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Guardian Agent 返回错误：{exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 Guardian Agent：{agent_url}，请确认 python server.py 正在运行。") from exc


def run_voice_turn(args: argparse.Namespace) -> None:
    service = load_voice_service(Path(args.voice_lab_dir))
    prompt = args.prompt or "检测到您已离床，需要帮助吗？"
    print(f"系统播报: {prompt}")
    service.speak(prompt)
    transcript = service.transcribe_recording()
    text = transcript.text.strip()
    print(f"识别结果: {text or '（没有识别到语音）'}")
    if not text:
        text = ""
    result = post_night_turn(
        agent_url=args.agent_url,
        elder_id=args.elder_id,
        event_id=args.event_id,
        session_id=args.session_id,
        text=text,
    )
    print(json.dumps(_compact_result(result), ensure_ascii=False, indent=2))
    reply_text = result.get("reply_text") or "我已记录。"
    print(f"Agent 回复: {reply_text}")
    service.speak(reply_text)


def run_text_turn(args: argparse.Namespace) -> None:
    text = args.text or input("请输入老人原话: ").strip()
    result = post_night_turn(
        agent_url=args.agent_url,
        elder_id=args.elder_id,
        event_id=args.event_id,
        session_id=args.session_id,
        text=text,
        source="voice_lab_text_test",
    )
    print(json.dumps(_compact_result(result), ensure_ascii=False, indent=2))


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": result.get("intent"),
        "feedback_type": result.get("feedback_type"),
        "confidence": result.get("confidence"),
        "requires_clarification": result.get("requires_clarification"),
        "event_id": result.get("event_id"),
        "event_status": result.get("event_status"),
        "risk_level": result.get("risk_level"),
        "reply_text": result.get("reply_text"),
    }


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--voice-lab-dir",
        default=argparse.SUPPRESS,
        help="voice_lab directory containing voice_lab.py.",
    )
    parser.add_argument(
        "--agent-url",
        default=argparse.SUPPRESS,
        help="Guardian night-turn endpoint.",
    )
    parser.add_argument("--elder-id", default=argparse.SUPPRESS)
    parser.add_argument("--event-id", default=argparse.SUPPRESS)
    parser.add_argument("--session-id", default=argparse.SUPPRESS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge voice_lab STT/TTS with Guardian night-turn.")
    parser.set_defaults(
        voice_lab_dir=str(DEFAULT_VOICE_LAB_DIR),
        agent_url=DEFAULT_AGENT_URL,
        elder_id="E001",
        event_id="",
        session_id="",
    )
    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    voice_parser = subparsers.add_parser("voice", help="Speak prompt, record microphone, send STT text to Agent, then TTS reply.")
    add_common_arguments(voice_parser)
    voice_parser.add_argument("--prompt", default="")

    text_parser = subparsers.add_parser("text", help="Send typed text to Agent without microphone.")
    add_common_arguments(text_parser)
    text_parser.add_argument("text", nargs="?", default="")

    args = parser.parse_args()
    if args.command == "voice":
        run_voice_turn(args)
    elif args.command == "text":
        run_text_turn(args)


if __name__ == "__main__":
    main()
