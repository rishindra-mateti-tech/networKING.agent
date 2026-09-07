"""
Runs every test module and exits non-zero if any check failed.

    python tests/run_all.py

No test framework required: the suite runs on the same interpreter as the app.
It writes to a temporary database (see _harness.py), never the real one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_cross_tenant
import test_generation_robustness
import test_grounding
import test_parsing_and_uploads

MODULES = [
    test_cross_tenant,
    test_parsing_and_uploads,
    test_generation_robustness,
    test_grounding,
]


def main():
    results = [(module.__name__, module.run()) for module in MODULES]

    print("\n" + "=" * 62)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [name for name, ok in results if not ok]
    print("=" * 62)
    if failed:
        print(f"{len(failed)} module(s) failed: {', '.join(failed)}")
        return 1
    print("All suites passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
