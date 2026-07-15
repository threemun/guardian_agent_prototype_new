from __future__ import annotations

import argparse
import json

from agent.db import get_conn, init_db
from agent.message import process_guardian_message
from agent.seed import seed_demo_data
from simulator.scenarios import scenario_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a GuardianMessage simulator scenario.")
    parser.add_argument("scenario_code", help="Scenario code, such as normal_bathroom or fall_detected.")
    parser.add_argument("--elder-id", default="E001", help="Demo elder id. Defaults to E001.")
    parser.add_argument("--reset", action="store_true", help="Reset and seed the demo database before running.")
    args = parser.parse_args()

    if args.reset:
        seed_demo_data(reset=True)
    else:
        init_db(reset=False)

    payload = scenario_payload(args.scenario_code, args.elder_id)
    results = []
    with get_conn() as conn:
        for message in payload["messages"]:
            results.append(process_guardian_message(conn, message))

    print(json.dumps({**payload, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
