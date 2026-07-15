from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "night_turn_cases_v1.json"
RESULT_FIELDS = {
    "intent": "expected_intent",
    "status": "expected_status",
    "risk": "expected_risk",
    "requires_clarification": "requires_clarification",
    "must_escalate": "must_escalate",
}


def load_cases() -> list[dict[str, Any]]:
    document = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if document.get("contract_version") != "1.0":
        raise ValueError("night-turn eval contract_version must be 1.0")
    return document["cases"]


def load_results(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("contract_version") != "1.0":
        raise ValueError("Agent result contract_version must be 1.0")
    return document["results"]


def score_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    cases = load_cases()
    results_by_id = {item["id"]: item for item in results}
    failures: list[dict[str, Any]] = []

    for case in cases:
        actual = results_by_id.get(case["id"])
        if actual is None:
            failures.append({"case": case, "actual": None, "checks": {"result_present": False}})
            continue
        checks = {
            actual_field: actual.get(actual_field) == case[expected_field]
            for actual_field, expected_field in RESULT_FIELDS.items()
        }
        if not all(checks.values()):
            failures.append({"case": case, "actual": actual, "checks": checks})

    expected_ids = {case["id"] for case in cases}
    unexpected_ids = sorted(set(results_by_id) - expected_ids)
    return {
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failures": failures,
        "unexpected_ids": unexpected_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Tuya Agent night-turn results against Evals v1.")
    parser.add_argument("--results", required=True, type=Path, help="JSON file exported from the Tuya Agent run")
    args = parser.parse_args()

    result = score_results(load_results(args.results))
    total = result["total"]
    passed = result["passed"]
    print(f"Night-turn Agent eval: {passed}/{total} passed ({passed / total:.1%})")
    for item in result["failures"]:
        case = item["case"]
        print(f"- {case['id']}: {case['text']!r}")
        print(f"  failed checks: {[name for name, ok in item['checks'].items() if not ok]}")
        print(f"  actual: {item['actual']}")
    if result["unexpected_ids"]:
        print(f"Unexpected result ids: {result['unexpected_ids']}")
    if result["failures"] or result["unexpected_ids"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
