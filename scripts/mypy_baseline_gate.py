"""Phase 6: makes mypy an actual CI gate without requiring the ~166 pre-existing errors in
untouched legacy modules (mostly app/services/rag.py at 44, plus dashboard.py, settings.py,
dental_records.py) to be fixed first - blindly adding type annotations across code this
pass didn't otherwise touch risks introducing behavior bugs under time pressure, which is
worse than the status quo. `mypy app/ --ignore-missing-imports || true` could never fail
the build regardless of how many NEW errors a change introduced; this can.

This is a ratchet, not a permanent exemption: it fails the build if the error count goes
UP from the committed baseline, and prints a reminder to lower the baseline whenever a fix
brings the count down. Every module actually touched during this hardening pass
(app/core/resilience.py, concurrency.py, encryption.py, token_blocklist.py, audit.py,
app/services/degradation.py, retrieval_cache.py, embeddings.py, memory.py, and the parts
of app/agent/graph.py this pass added) is already at zero errors - confirmed individually,
not just netted against the total - so the remaining baseline is legacy debt, not new
debt this pass introduced or is hiding.

Usage:
    python scripts/mypy_baseline_gate.py            # check against the baseline
    python scripts/mypy_baseline_gate.py --update   # rewrite the baseline to the current count
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parents[1] / "mypy_baseline.txt"


def run_mypy() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "app/", "--ignore-missing-imports"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    for line in reversed(output.splitlines()):
        if line.startswith("Found ") and " errors in " in line:
            return int(line.split()[1]), output
        if line.strip() == "Success: no issues found in 72 source files":
            return 0, output
    # mypy prints nothing matching either pattern only on an unexpected failure (e.g. a
    # crash) - treat that as a hard failure rather than silently reporting 0 errors.
    print("mypy_baseline_gate: could not parse an error count from mypy's output:", file=sys.stderr)
    print(output, file=sys.stderr)
    sys.exit(1)


def main() -> int:
    update = "--update" in sys.argv
    current_count, output = run_mypy()

    if update:
        BASELINE_PATH.write_text(str(current_count) + "\n")
        print(f"mypy_baseline_gate: baseline updated to {current_count}")
        return 0

    if not BASELINE_PATH.exists():
        print(f"mypy_baseline_gate: no baseline file at {BASELINE_PATH} - run with --update first.", file=sys.stderr)
        return 1

    baseline_count = int(BASELINE_PATH.read_text().strip())
    print(f"mypy_baseline_gate: current={current_count} baseline={baseline_count}")

    if current_count > baseline_count:
        print(
            f"mypy_baseline_gate: FAILED - {current_count - baseline_count} new type error(s) "
            f"introduced beyond the {baseline_count}-error baseline.",
            file=sys.stderr,
        )
        print(output, file=sys.stderr)
        return 1

    if current_count < baseline_count:
        print(
            f"mypy_baseline_gate: error count dropped ({baseline_count} -> {current_count}) - "
            "run with --update to lock in the improvement."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
