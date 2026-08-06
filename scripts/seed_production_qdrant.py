"""One-time seed: build the ACTIVE Qdrant collection (as configured by
QDRANT_COLLECTION) from the reviewed, non-noisy chunks now in the database.

Reuses the selection/embedding logic from rebuild_clean_qdrant.py, but
targets the real active collection directly. That script deliberately
refuses to write into the active collection - a safety guard for its
normal "build a candidate collection to review" workflow - which doesn't
apply here since the active collection starts out genuinely empty.

Run inside the api container:
    docker compose -f docker-compose.dev.yml exec -T api \\
        python scripts/seed_production_qdrant.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import init_db  # noqa: E402
from rebuild_clean_qdrant import collect_clean_records, rebuild_collection  # noqa: E402


def main() -> None:
    settings = get_settings()
    init_db()

    docs, chunks, visuals, skipped = collect_clean_records(
        min_quality=0.6,
        trust_levels={"high", "medium"},
        review_statuses={"approved", "reviewed"},
        include_visuals=False,
    )
    print(f"Selected {len(docs)} documents, {len(chunks)} chunks (skipped: {skipped})")

    if not chunks:
        print("Nothing to seed - exiting.")
        return

    summary = rebuild_collection(
        target_collection=settings.qdrant_collection,
        chunks=chunks,
        visuals=[],
        replace_target=False,
        batch_size=64,
    )
    print(summary)


if __name__ == "__main__":
    main()
