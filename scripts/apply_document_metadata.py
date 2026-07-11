from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

from apply_retained_chunk_cleanup import (
    DOC_COLUMNS,
    ensure_schema,
    infer_author,
    infer_publication_year,
    infer_publisher,
    infer_topic,
)
from cleanup_audit_lib import (
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    canonical_title,
    connect,
    content_hash,
    infer_difficulty,
    infer_document_type,
    infer_language,
    infer_specialty,
    infer_trust,
    load_documents,
    report_dir,
)


FINAL_FIELDS = [
    "document_id",
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


def backup_db(db_path: Path, reports: Path) -> Path:
    backup_dir = PROJECT_ROOT / "backups" / f"document_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / db_path.name
    shutil.copy2(db_path, target)
    (reports / "document_metadata_backup_path.txt").write_text(str(target), encoding="utf-8")
    return target


def build_rows(db_path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for doc in load_documents(db_path):
        title = canonical_title(doc)
        dental_specialty = infer_specialty(doc)
        topic = infer_topic(f"{title} {doc.original_filename}", dental_specialty)
        trust_level = infer_trust(doc, "KEEP")
        rows.append(
            {
                "document_id": doc.id,
                "canonical_title": title,
                "original_filename": doc.original_filename,
                "author": infer_author(doc.original_filename, doc.author_or_source),
                "publisher": infer_publisher(doc.original_filename),
                "publication_year": infer_publication_year(f"{title} {doc.original_filename}", doc.publication_year),
                "edition": doc.edition or "Unknown",
                "document_type": infer_document_type(doc),
                "dental_specialty": dental_specialty,
                "topic": topic,
                "difficulty_level": infer_difficulty(doc),
                "language": infer_language(doc)[0],
                "trust_level": trust_level,
                "review_status": "reviewed" if trust_level in {"high", "medium"} else "unreviewed",
                "duplicate_group_id": "none",
                "content_hash": content_hash(" ".join(chunk.text[:1000] for chunk in doc.chunks[:12])),
                "extraction_method": "ocr" if doc.ocr_used else "pdf_text",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FINAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply and export final document-level metadata.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--report-dir", default="cleanup_reports_retained_apply")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    reports = report_dir(PROJECT_ROOT / args.report_dir)
    rows = build_rows(db_path)
    write_csv(reports / "document_metadata_final.csv", rows)

    if not args.apply:
        print(f"Dry-run export written: {reports / 'document_metadata_final.csv'}")
        return

    backup_path = backup_db(db_path, reports)
    with connect(db_path) as conn:
        ensure_schema(conn)
        for row in rows:
            conn.execute(
                """
                UPDATE documents
                SET canonical_title = ?, title = ?, author = ?, author_or_source = ?,
                    publisher = ?, publication_year = ?, edition = ?, document_type = ?,
                    dental_specialty = ?, specialty = ?, topic = ?, difficulty_level = ?,
                    language = ?, trust_level = ?, review_status = ?, duplicate_group_id = ?,
                    content_hash = ?, extraction_method = ?
                WHERE id = ?
                """,
                (
                    row["canonical_title"],
                    row["canonical_title"],
                    row["author"],
                    row["author"],
                    row["publisher"],
                    row["publication_year"],
                    row["edition"],
                    row["document_type"],
                    row["dental_specialty"],
                    row["dental_specialty"],
                    row["topic"],
                    row["difficulty_level"],
                    row["language"],
                    row["trust_level"],
                    row["review_status"],
                    row["duplicate_group_id"],
                    row["content_hash"],
                    row["extraction_method"],
                    row["document_id"],
                ),
            )
        conn.commit()
    print(f"Applied metadata for {len(rows)} documents.")
    print(f"Backup DB: {backup_path}")
    print(f"Export: {reports / 'document_metadata_final.csv'}")


if __name__ == "__main__":
    main()
