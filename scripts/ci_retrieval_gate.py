"""CI gate for retrieval/citation quality (Phase 5/6).

scripts/evaluate_rag.py and docs/evaluation_dataset.jsonl (30 labeled cases) already
existed and worked, but were never run anywhere - not in CI, not documented as a manual
step. This wraps that script for CI: if a real, populated Qdrant collection is reachable,
it runs the evaluation and FAILS THE BUILD if the pass rate drops below a threshold. If no
such Qdrant is reachable (true for a plain CI runner today - see
.github/workflows/ci-cd.yml, which only starts Postgres+Redis service containers, not
Qdrant, per Phase 0 finding #14's context), it skips with a clear warning instead of
failing the build on missing infrastructure it was never asked to provide.

To make this a REAL, always-enforced gate rather than a conditional one: restore a
pinned Qdrant snapshot (a small, fixed subset of the real corpus covering the eval
dataset's topics) as a CI step before this runs, and pass --require-qdrant to make a
missing/empty Qdrant a hard failure instead of a skip.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _qdrant_has_data() -> bool:
    try:
        from app.core.config import get_settings
        from app.services.vector_store import collection_exists, get_qdrant_client

        settings = get_settings()
        client = get_qdrant_client()
        if not collection_exists(client, settings.qdrant_collection):
            return False
        count = client.count(collection_name=settings.qdrant_collection, exact=False)
        return (count.count if hasattr(count, "count") else count) > 0
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="CI gate wrapping scripts/evaluate_rag.py")
    parser.add_argument("--dataset", default="docs/evaluation_dataset.jsonl")
    parser.add_argument("--min-pass-rate", type=float, default=0.7, help="Fail the build below this pass rate.")
    parser.add_argument("--min-citation-rate", type=float, default=0.8, help="Fail the build below this citation rate.")
    parser.add_argument(
        "--require-qdrant",
        action="store_true",
        help="Treat an unreachable/empty Qdrant as a failure instead of a skip. Only pass "
        "this once CI actually provisions a populated Qdrant (see module docstring).",
    )
    args = parser.parse_args()

    if not _qdrant_has_data():
        message = "ci_retrieval_gate: no populated Qdrant collection reachable - "
        if args.require_qdrant:
            print(message + "failing because --require-qdrant was set.", file=sys.stderr)
            return 1
        print(message + "skipping retrieval quality gate (see script docstring to make this a hard gate).")
        return 0

    from app.services.evaluation import evaluate_cases, load_evaluation_cases, summarize_results
    from app.services.rag import RAGService

    cases = load_evaluation_cases(Path(args.dataset))
    if not cases:
        print(f"ci_retrieval_gate: no cases loaded from {args.dataset}", file=sys.stderr)
        return 1

    service = RAGService()
    results = evaluate_cases(service, cases)
    summary = summarize_results(results)
    print(f"ci_retrieval_gate: {summary}")

    failed = []
    if summary["pass_rate"] < args.min_pass_rate:
        failed.append(f"pass_rate {summary['pass_rate']:.2f} < {args.min_pass_rate}")
    if summary["citation_rate"] < args.min_citation_rate:
        failed.append(f"citation_rate {summary['citation_rate']:.2f} < {args.min_citation_rate}")

    if failed:
        print("ci_retrieval_gate: FAILED - " + "; ".join(failed), file=sys.stderr)
        return 1

    print("ci_retrieval_gate: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
