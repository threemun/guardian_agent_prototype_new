from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.conversation import classify_elder_reply

CASES_PATH = ROOT / "night_turn_cases.json"


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures: list[dict] = []
    for case in cases:
        actual = classify_elder_reply(case["text"])
        checks = {
            "intent": actual["intent"] == case["expected_intent"],
            "feedback_type": actual["feedback_type"] == case["expected_feedback_type"],
            "requires_clarification": actual["requires_clarification"] == case["expected_requires_clarification"],
        }
        if not all(checks.values()):
            failures.append({"case": case, "actual": actual, "checks": checks})

    passed = len(cases) - len(failures)
    print(f"Night-turn intent eval: {passed}/{len(cases)} passed ({passed / len(cases):.1%})")
    if failures:
        print("\nFailures:")
        for item in failures:
            case = item["case"]
            actual = item["actual"]
            print(f"- {case['id']}: {case['text']!r}")
            print(
                "  expected "
                f"intent={case['expected_intent']}, "
                f"feedback={case['expected_feedback_type']}, "
                f"clarify={case['expected_requires_clarification']}"
            )
            print(
                "  actual   "
                f"intent={actual['intent']}, "
                f"feedback={actual['feedback_type']}, "
                f"clarify={actual['requires_clarification']}, "
                f"analysis={actual['analysis']}"
            )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
