"""Verify that a Naatomatic database satisfies every hard constraint (HC-*).

Usage:
    python scripts/verify.py [--db PATH]

Runs all checks in rules/constraints.py. Prints PASS/FAIL per rule and exits
non-zero if any rule is violated (so it can gate CI / pre-commit later).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.db import DEFAULT_DB_PATH, create_session, get_engine
from rules.constraints import ALL_CHECKS, run_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify hard constraints over the database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite path")
    parser.add_argument("--max-show", type=int, default=5, help="max violations to print per rule")
    args = parser.parse_args()

    session = create_session(get_engine(args.db))
    try:
        results = run_all(session)
    finally:
        session.close()

    descriptions = {c.code: c.description for c in ALL_CHECKS}
    total_violations = 0
    print(f"Verifying {args.db}\n")
    for code in (c.code for c in ALL_CHECKS):
        violations = results[code]
        total_violations += len(violations)
        if not violations:
            print(f"  [PASS] {code:9} {descriptions[code]}")
        else:
            print(f"  [FAIL] {code:9} {descriptions[code]} - {len(violations)} violation(s)")
            for v in violations[: args.max_show]:
                print(f"            - {v}")
            if len(violations) > args.max_show:
                print(f"            ... and {len(violations) - args.max_show} more")

    print()
    if total_violations == 0:
        print("All hard constraints satisfied. [OK]")
        return 0
    print(f"{total_violations} total violation(s) across rules. [FAIL]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
