from __future__ import annotations

import sqlite3

from cleanup_audit_lib import DEFAULT_DB_PATH


REQUIRED_COLUMNS = [
    "id",
    "canonical_title",
    "original_filename",
    "author",
    "publisher",
    "publication_year",
    "edition",
    "document_type",
    "dental_specialty",
    "topic",
    "difficulty_level",
    "language",
    "trust_level",
    "review_status",
    "duplicate_group_id",
    "content_hash",
    "extraction_method",
]


def main() -> None:
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        print(f"documents: {total}")
        print(f"missing_columns: {missing_columns}")
        for column in REQUIRED_COLUMNS:
            if column == "id" or column not in columns:
                continue
            missing = conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE {column} IS NULL OR {column} = ''"
            ).fetchone()[0]
            print(f"missing_{column}: {missing}")


if __name__ == "__main__":
    main()
