from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cleanup_audit_lib import DEFAULT_DB_PATH, DEFAULT_REPORT_DIR


def main() -> None:
    summary_path = Path(DEFAULT_REPORT_DIR) / "applied_cleanup_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    removed = summary.get("documents", [])
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        print(f"active documents: {doc_count}")
        print(f"active chunks: {chunk_count}")
        for row in removed:
            doc_id = row["document_id"]
            exists = conn.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]
            print(f"removed_check: {row['original_filename']} | db_exists={exists} | chunks={chunks}")


if __name__ == "__main__":
    main()
