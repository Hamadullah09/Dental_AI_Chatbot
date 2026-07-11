from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from cleanup_audit_lib import DEFAULT_DB_PATH, DEFAULT_REPORT_DIR, PROJECT_ROOT, connect, report_dir, write_json

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


EXTRA_REMOVE_PATTERNS = [
    "spss",
    "conference",
    "brochure",
    "registration form",
    "regn. form",
    "table-of-contents",
    "table of contents",
    "ed-board",
    "editorial board",
    "future-issues",
    "future issues",
]


def load_report_document_ids(report_path: Path) -> dict[str, str]:
    decisions: dict[str, str] = {}
    if not report_path.exists():
        return decisions
    with report_path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            doc_id = row.get("document_id", "").strip()
            classification = row.get("classification", "").strip()
            if doc_id and classification in {"DUPLICATE", "QUARANTINE", "REMOVE_CANDIDATE"}:
                decisions[doc_id] = classification
    return decisions


def load_extra_document_ids(conn: sqlite3.Connection) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for row in conn.execute("SELECT id, original_filename, title FROM documents"):
        haystack = f"{row['original_filename'] or ''} {row['title'] or ''}".lower()
        if any(pattern in haystack for pattern in EXTRA_REMOVE_PATTERNS):
            decisions[row["id"]] = "QUARANTINE"
    return decisions


def copy_backup(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / db_path.name
    shutil.copy2(db_path, target)
    return target


def quarantine_file(storage_path: str, quarantine_dir: Path, document_id: str) -> str:
    source = Path(storage_path)
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    if not source.exists() or not source.is_file():
        return ""
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / f"{document_id}_{source.name}"
    if not target.exists():
        shutil.move(str(source), str(target))
    return str(target)


def delete_qdrant_vectors(document_ids: list[str]) -> dict[str, str]:
    if not document_ids:
        return {}
    try:
        from app.core.config import get_settings
        from app.services.vector_store import get_qdrant_client
        from qdrant_client.http import models as qmodels

        settings = get_settings()
        qdrant = get_qdrant_client()
        results: dict[str, str] = {}
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
            results[document_id] = "deleted"
        return results
    except Exception as exc:
        return {"__error__": str(exc)}


def apply_db_cleanup(conn: sqlite3.Connection, decisions: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for document_id, action in decisions.items():
        document = conn.execute(
            "SELECT id, original_filename, storage_path FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not document:
            continue
        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM document_ingestion_logs WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        rows.append(
            {
                "document_id": document_id,
                "action": action,
                "original_filename": document["original_filename"] or "",
                "storage_path": document["storage_path"] or "",
                "deleted_chunks": str(chunk_count),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply reviewed Dental AI cleanup decisions with DB backup and raw-file quarantine."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--apply", action="store_true", help="Required to mutate the active DB and quarantine files.")
    parser.add_argument("--skip-qdrant", action="store_true", help="Skip deleting vectors from the current Qdrant collection.")
    args = parser.parse_args()

    if not args.apply:
        raise SystemExit("Dry-run only. Add --apply to remove reviewed documents from active DB.")

    db_path = Path(args.db)
    reports = report_dir(args.report_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT_ROOT / "backups" / f"cleanup_{timestamp}"
    quarantine_dir = backup_dir / "quarantined_uploaded_docs"
    backup_db_path = copy_backup(db_path, backup_dir)

    with connect(db_path) as conn:
        decisions = load_report_document_ids(reports / "removal_candidates.csv")
        decisions.update(load_extra_document_ids(conn))
        target_ids = sorted(decisions)

        quarantined: dict[str, str] = {}
        for document_id in target_ids:
            row = conn.execute("SELECT storage_path FROM documents WHERE id = ?", (document_id,)).fetchone()
            if row:
                quarantined[document_id] = quarantine_file(row["storage_path"], quarantine_dir, document_id)

        qdrant_results = {} if args.skip_qdrant else delete_qdrant_vectors(target_ids)
        applied_rows = apply_db_cleanup(conn, decisions)
        conn.commit()

    summary = {
        "mode": "applied",
        "backup_db_path": str(backup_db_path),
        "quarantine_dir": str(quarantine_dir),
        "documents_removed_from_active_db": len(applied_rows),
        "chunks_removed_from_active_db": sum(int(row["deleted_chunks"]) for row in applied_rows),
        "qdrant_results": qdrant_results,
        "documents": [
            {
                **row,
                "quarantined_path": quarantined.get(row["document_id"], ""),
            }
            for row in applied_rows
        ],
    }
    write_json(reports / "applied_cleanup_summary.json", summary)
    print(f"Backup DB: {backup_db_path}")
    print(f"Quarantine dir: {quarantine_dir}")
    print(f"Documents removed from active DB: {summary['documents_removed_from_active_db']}")
    print(f"Chunks removed from active DB: {summary['chunks_removed_from_active_db']}")
    if qdrant_results.get("__error__"):
        print(f"Qdrant cleanup warning: {qdrant_results['__error__']}")
    print(f"Applied cleanup report: {reports / 'applied_cleanup_summary.json'}")


if __name__ == "__main__":
    main()
