from __future__ import annotations

import sqlite3

from cleanup_audit_lib import DEFAULT_DB_PATH


def main() -> None:
    missing_chunk_hash_sql = "SELECT COUNT(*) FROM document_chunks WHERE content_hash IS NULL OR content_hash = ''"
    missing_doc_hash_sql = "SELECT COUNT(*) FROM documents WHERE content_hash IS NULL OR content_hash = ''"
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        print(f"documents: {conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]}")
        print(f"chunks: {conn.execute('SELECT COUNT(*) FROM document_chunks').fetchone()[0]}")
        print(
            "duplicate_chunk_references: "
            f"{conn.execute('SELECT COUNT(*) FROM duplicate_chunk_references').fetchone()[0]}"
        )
        print(
            "noisy_chunks_remaining: "
            f"{conn.execute('SELECT COUNT(*) FROM document_chunks WHERE is_noisy = 1').fetchone()[0]}"
        )
        print(
            "missing_chunk_content_hash: "
            f"{conn.execute(missing_chunk_hash_sql).fetchone()[0]}"
        )
        print(
            "missing_document_content_hash: "
            f"{conn.execute(missing_doc_hash_sql).fetchone()[0]}"
        )


if __name__ == "__main__":
    main()
