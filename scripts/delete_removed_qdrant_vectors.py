from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cleanup_audit_lib import DEFAULT_REPORT_DIR, PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete Qdrant vectors for documents removed by cleanup.")
    parser.add_argument("--summary", default=str(Path(DEFAULT_REPORT_DIR) / "applied_cleanup_summary.json"))
    args = parser.parse_args()

    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    document_ids = [row["document_id"] for row in summary.get("documents", []) if row.get("document_id")]
    if not document_ids:
        print("No removed document IDs found.")
        return

    from app.core.config import get_settings
    from app.services.vector_store import get_qdrant_client
    from qdrant_client.http import models as qmodels

    settings = get_settings()
    try:
        qdrant = get_qdrant_client()
    except RuntimeError as exc:
        message = str(exc)
        if "already accessed by another instance" in message or "Storage folder" in message:
            print("Qdrant local storage is locked by another running process.")
            print("Stop the backend first, then run this command again:")
            print(r".run_venv\Scripts\python.exe scripts\delete_removed_qdrant_vectors.py")
            print("After it finishes, restart the backend:")
            print(r".\scripts\start_backend.ps1")
            return
        raise
    for document_id in document_ids:
        qdrant.delete(
            collection_name=settings.qdrant_collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        print(f"Deleted vectors for document_id={document_id}")

    print(f"Deleted Qdrant vectors for {len(document_ids)} removed documents.")


if __name__ == "__main__":
    main()
