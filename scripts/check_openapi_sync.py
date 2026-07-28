"""Phase 7: keeps docs/openapi.json in sync with what the FastAPI app actually serves.

Nothing previously checked that the committed API documentation matched the real
schema - a route's request/response model could drift (a field added, removed, or
renamed) with no CI signal that docs/openapi.json (or any external API consumer relying
on it) had gone stale. This is the same category of gap tests/test_api_contracts.py
targets from the test side (Phase 6) - this script targets the generated-documentation
side.

Usage:
    python scripts/check_openapi_sync.py            # fail if docs/openapi.json is stale
    python scripts/check_openapi_sync.py --update    # regenerate docs/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "openapi.json"


def _current_schema() -> dict[str, Any]:
    from app.main import app

    return dict(app.openapi())


def main() -> int:
    update = "--update" in sys.argv
    current = _current_schema()
    current_text = json.dumps(current, indent=2, sort_keys=True) + "\n"

    if update:
        SNAPSHOT_PATH.write_text(current_text, encoding="utf-8")
        print(f"check_openapi_sync: wrote {SNAPSHOT_PATH}")
        return 0

    if not SNAPSHOT_PATH.exists():
        print(f"check_openapi_sync: no snapshot at {SNAPSHOT_PATH} - run with --update first.", file=sys.stderr)
        return 1

    committed_text = SNAPSHOT_PATH.read_text(encoding="utf-8")
    if committed_text == current_text:
        print("check_openapi_sync: docs/openapi.json is in sync.")
        return 0

    print(
        "check_openapi_sync: FAILED - docs/openapi.json is out of sync with the actual "
        "FastAPI schema. A route's request/response model, path, or metadata changed "
        "without regenerating the committed snapshot.\n"
        "Run `python scripts/check_openapi_sync.py --update` and commit the result.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
