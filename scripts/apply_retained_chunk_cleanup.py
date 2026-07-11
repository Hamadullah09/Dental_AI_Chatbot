from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cleanup_audit_lib import (
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    assess_text_quality,
    canonical_title,
    clean_chunk_text,
    connect,
    content_hash,
    infer_difficulty,
    infer_document_type,
    infer_language,
    infer_specialty,
    infer_trust,
    load_documents,
    normalize_text_for_hash,
    report_dir,
    write_json,
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DOC_COLUMNS = {
    "canonical_title": "TEXT",
    "author": "TEXT",
    "publisher": "TEXT",
    "dental_specialty": "TEXT",
    "topic": "TEXT",
    "difficulty_level": "TEXT",
    "duplicate_group_id": "TEXT",
    "content_hash": "TEXT",
    "extraction_method": "TEXT",
}

CHUNK_COLUMNS = {
    "canonical_document_title": "TEXT",
    "section_title": "TEXT",
    "chapter_title": "TEXT",
    "dental_specialty": "TEXT",
    "topic": "TEXT",
    "difficulty_level": "TEXT",
    "language": "TEXT",
    "trust_level": "TEXT",
    "review_status": "TEXT",
    "content_hash": "TEXT",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    document_columns = existing_columns(conn, "documents")
    chunk_columns = existing_columns(conn, "document_chunks")
    for name, ddl_type in DOC_COLUMNS.items():
        if name not in document_columns:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {ddl_type}")
    for name, ddl_type in CHUNK_COLUMNS.items():
        if name not in chunk_columns:
            conn.execute(f"ALTER TABLE document_chunks ADD COLUMN {name} {ddl_type}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_chunk_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_chunk_id TEXT NOT NULL,
            duplicate_chunk_id TEXT NOT NULL,
            duplicate_document_id TEXT NOT NULL,
            duplicate_document_title TEXT,
            duplicate_page_number INTEGER,
            duplicate_chunk_index INTEGER,
            duplicate_text_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def infer_publication_year(text: str, stored_year: int | None) -> int | None:
    if stored_year:
        return stored_year
    years = [int(match) for match in re.findall(r"\b(19[5-9]\d|20[0-3]\d)\b", text)]
    return max(years) if years else None


def infer_author(filename: str, current: str) -> str:
    if current:
        return current
    stem = Path(filename).stem
    match = re.match(r"([^_-]+?)\s+-\s+", stem)
    if match:
        return match.group(1).strip()
    paren = re.search(r"\(([^,()]+),\s*(?:19|20)\d{2}\)", stem)
    if paren:
        return paren.group(1).strip()
    return "Unknown"


def infer_publisher(filename: str) -> str:
    lower = filename.lower()
    publishers = {
        "quintessence": "Quintessence Publishing",
        "thieme": "Thieme",
        "elsevier": "Elsevier",
        "wiley": "Wiley",
        "springer": "Springer",
        "mosby": "Mosby",
        "z-library": "Z-Library source copy",
        "pdfdrive": "PDFDrive source copy",
    }
    for needle, publisher in publishers.items():
        if needle in lower:
            return publisher
    return "Unknown"


def infer_topic(title: str, specialty: str) -> str:
    lower = title.lower()
    topic_map = [
        ("caries", "dental_caries"),
        ("implant", "implants_and_temporary_anchorage"),
        ("anchorage", "orthodontic_anchorage"),
        ("ceph", "cephalometrics"),
        ("cleft", "cleft_lip_and_palate"),
        ("tmj", "temporomandibular_disorders"),
        ("temporomandibular", "temporomandibular_disorders"),
        ("orthognathic", "orthognathic_surgery"),
        ("trauma", "dental_trauma"),
        ("pregnancy", "medically_compromised_dentistry"),
        ("antibiotic", "medically_compromised_dentistry"),
        ("allerg", "medically_compromised_dentistry"),
        ("bracket", "orthodontic_appliances"),
        ("aligner", "aligner_therapy"),
        ("occlusion", "occlusion"),
    ]
    for needle, topic in topic_map:
        if needle in lower:
            return topic
    return specialty or "general_dentistry"


def section_title_from_text(text: str) -> str:
    first = text.strip().split(". ")[0].strip()
    if 8 <= len(first) <= 90 and not first.endswith("?"):
        return first[:90]
    return ""


def chunk_duplicate_groups(rows: list[dict[str, Any]]) -> tuple[set[str], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if len(row["cleaned_text"].split()) < 35:
            continue
        groups[row["content_hash"]].append(row)

    duplicate_ids: set[str] = set()
    references: list[dict[str, Any]] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        canonical = sorted(
            items,
            key=lambda item: (item["quality_score"], len(item["cleaned_text"]), item["trust_level"] == "high"),
            reverse=True,
        )[0]
        for item in items:
            if item["chunk_id"] == canonical["chunk_id"]:
                continue
            duplicate_ids.add(item["chunk_id"])
            references.append(
                {
                    "canonical_chunk_id": canonical["chunk_id"],
                    "duplicate_chunk_id": item["chunk_id"],
                    "duplicate_document_id": item["document_id"],
                    "duplicate_document_title": item["canonical_document_title"],
                    "duplicate_page_number": item["page_number"],
                    "duplicate_chunk_index": item["chunk_index"],
                    "duplicate_text_hash": item["content_hash"],
                }
            )
    return duplicate_ids, references


def backup_db(db_path: Path, report_root: Path) -> Path:
    backup_dir = PROJECT_ROOT / "backups" / f"retained_chunk_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / db_path.name
    shutil.copy2(db_path, target)
    (report_root / "backup_path.txt").write_text(str(target), encoding="utf-8")
    return target


def update_qdrant(retained_payloads: dict[str, dict[str, Any]], removed_point_ids: list[str]) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.services.vector_store import get_qdrant_client
    from qdrant_client.http import models as qmodels

    settings = get_settings()
    qdrant = get_qdrant_client()
    collection = settings.qdrant_collection
    if removed_point_ids:
        qdrant.delete(collection_name=collection, points_selector=removed_point_ids)

    updated = 0
    offset = None
    batch: list[qmodels.PointStruct] = []
    while True:
        records, offset = qdrant.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for record in records:
            point_id = str(record.id)
            payload = retained_payloads.get(point_id)
            if not payload or record.vector is None:
                continue
            existing_payload = dict(record.payload or {})
            existing_payload.update(payload)
            batch.append(qmodels.PointStruct(id=record.id, vector=record.vector, payload=existing_payload))
            if len(batch) >= 128:
                qdrant.upsert(collection_name=collection, points=batch)
                updated += len(batch)
                batch.clear()
        if offset is None:
            break
    if batch:
        qdrant.upsert(collection_name=collection, points=batch)
        updated += len(batch)
    return {"removed_points": len(removed_point_ids), "updated_payloads": updated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean retained chunks, enrich metadata, and update Qdrant payloads.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--report-dir", default="cleanup_reports_retained_apply")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    args = parser.parse_args()

    reports = report_dir(PROJECT_ROOT / args.report_dir)
    db_path = Path(args.db)
    docs = load_documents(db_path)
    chunk_rows: list[dict[str, Any]] = []
    doc_metadata: dict[str, dict[str, Any]] = {}

    for doc in docs:
        title = canonical_title(doc)
        specialty = infer_specialty(doc)
        topic = infer_topic(f"{title} {doc.original_filename}", specialty)
        difficulty = infer_difficulty(doc)
        language = infer_language(doc)[0]
        doc_type = infer_document_type(doc)
        trust = infer_trust(doc, "KEEP")
        review_status = "reviewed" if trust in {"high", "medium"} else "unreviewed"
        year = infer_publication_year(f"{title} {doc.original_filename}", doc.publication_year)
        doc_text_hash = content_hash(" ".join(chunk.text[:1000] for chunk in doc.chunks[:12]))
        doc_metadata[doc.id] = {
            "canonical_title": title,
            "author": infer_author(doc.original_filename, doc.author_or_source),
            "publisher": infer_publisher(doc.original_filename),
            "publication_year": year,
            "edition": doc.edition or "Unknown",
            "document_type": doc_type,
            "dental_specialty": specialty,
            "topic": topic,
            "difficulty_level": difficulty,
            "language": language,
            "trust_level": trust,
            "review_status": review_status,
            "duplicate_group_id": "none",
            "content_hash": doc_text_hash,
            "extraction_method": "ocr" if doc.ocr_used else "pdf_text",
        }
        for chunk in doc.chunks:
            cleaned = clean_chunk_text(chunk.text)
            noisy, local_reasons, local_score = assess_text_quality(cleaned)
            reasons = sorted(set(chunk.noise_reasons + local_reasons))
            quality_score = min(float(chunk.quality_score or 1.0), local_score)
            is_noisy = bool(chunk.is_noisy or noisy or quality_score < 0.6 or len(cleaned.split()) < 35)
            chunk_rows.append(
                {
                    "row_id": chunk.id,
                    "chunk_id": chunk.qdrant_point_id,
                    "document_id": doc.id,
                    "cleaned_text": cleaned,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "canonical_document_title": title,
                    "section_title": section_title_from_text(cleaned),
                    "chapter_title": "",
                    "dental_specialty": specialty,
                    "topic": topic,
                    "difficulty_level": difficulty,
                    "language": language,
                    "trust_level": trust,
                    "quality_score": quality_score,
                    "is_noisy": is_noisy,
                    "noise_reasons": reasons,
                    "review_status": "reject" if is_noisy else "reviewed",
                    "content_hash": content_hash(cleaned),
                }
            )

    noisy_ids = {row["chunk_id"] for row in chunk_rows if row["is_noisy"]}
    duplicate_ids, duplicate_refs = chunk_duplicate_groups([row for row in chunk_rows if row["chunk_id"] not in noisy_ids])
    removed_ids = noisy_ids | duplicate_ids
    retained_rows = [row for row in chunk_rows if row["chunk_id"] not in removed_ids]

    summary = {
        "mode": "apply" if args.apply else "dry_run",
        "documents_enriched": len(doc_metadata),
        "chunks_before": len(chunk_rows),
        "noisy_chunks_removed": len(noisy_ids),
        "duplicate_chunks_removed": len(duplicate_ids),
        "chunks_remaining": len(retained_rows),
        "duplicate_source_references_preserved": len(duplicate_refs),
        "qdrant": "skipped",
    }
    write_json(reports / "retained_chunk_cleanup_summary.json", summary)

    if not args.apply:
        print("Dry-run only. Add --apply to mutate DB/Qdrant.")
        print(json.dumps(summary, indent=2))
        return

    backup_path = backup_db(db_path, reports)
    retained_payloads: dict[str, dict[str, Any]] = {}
    with connect(db_path) as conn:
        ensure_schema(conn)
        for doc_id, metadata in doc_metadata.items():
            conn.execute(
                """
                UPDATE documents
                SET title = ?, canonical_title = ?, author = ?, author_or_source = ?,
                    publisher = ?, publication_year = ?, document_type = ?,
                    dental_specialty = ?, specialty = ?, topic = ?, difficulty_level = ?,
                    language = ?, trust_level = ?, review_status = ?, duplicate_group_id = ?,
                    content_hash = ?, extraction_method = ?
                WHERE id = ?
                """,
                (
                    metadata["canonical_title"],
                    metadata["canonical_title"],
                    metadata["author"],
                    metadata["author"],
                    metadata["publisher"],
                    metadata["publication_year"],
                    metadata["document_type"],
                    metadata["dental_specialty"],
                    metadata["dental_specialty"],
                    metadata["topic"],
                    metadata["difficulty_level"],
                    metadata["language"],
                    metadata["trust_level"],
                    metadata["review_status"],
                    metadata["duplicate_group_id"],
                    metadata["content_hash"],
                    metadata["extraction_method"],
                    doc_id,
                ),
            )
        conn.execute("DELETE FROM duplicate_chunk_references")
        for ref in duplicate_refs:
            conn.execute(
                """
                INSERT INTO duplicate_chunk_references (
                    canonical_chunk_id, duplicate_chunk_id, duplicate_document_id,
                    duplicate_document_title, duplicate_page_number, duplicate_chunk_index,
                    duplicate_text_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ref["canonical_chunk_id"],
                    ref["duplicate_chunk_id"],
                    ref["duplicate_document_id"],
                    ref["duplicate_document_title"],
                    ref["duplicate_page_number"],
                    ref["duplicate_chunk_index"],
                    ref["duplicate_text_hash"],
                ),
            )
        for row in retained_rows:
            conn.execute(
                """
                UPDATE document_chunks
                SET text = ?, token_estimate = ?, quality_score = ?, is_noisy = 0,
                    noise_reasons = ?, canonical_document_title = ?, section_title = ?,
                    chapter_title = ?, dental_specialty = ?, topic = ?, difficulty_level = ?,
                    language = ?, trust_level = ?, review_status = ?, content_hash = ?
                WHERE qdrant_point_id = ?
                """,
                (
                    row["cleaned_text"],
                    max(1, len(row["cleaned_text"].split())),
                    row["quality_score"],
                    json.dumps(row["noise_reasons"], ensure_ascii=False),
                    row["canonical_document_title"],
                    row["section_title"],
                    row["chapter_title"],
                    row["dental_specialty"],
                    row["topic"],
                    row["difficulty_level"],
                    row["language"],
                    row["trust_level"],
                    row["review_status"],
                    row["content_hash"],
                    row["chunk_id"],
                ),
            )
            retained_payloads[row["chunk_id"]] = {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "canonical_document_title": row["canonical_document_title"],
                "book_title": row["canonical_document_title"],
                "title": row["canonical_document_title"],
                "page_number": row["page_number"],
                "chunk_index": row["chunk_index"],
                "section_title": row["section_title"],
                "chapter_title": row["chapter_title"],
                "dental_specialty": row["dental_specialty"],
                "specialty": row["dental_specialty"],
                "topic": row["topic"],
                "difficulty_level": row["difficulty_level"],
                "language": row["language"],
                "trust_level": row["trust_level"],
                "quality_score": row["quality_score"],
                "is_noisy": False,
                "noise_reasons": row["noise_reasons"],
                "review_status": row["review_status"],
                "content_hash": row["content_hash"],
                "text": row["cleaned_text"],
            }
        if removed_ids:
            placeholders = ",".join("?" for _ in removed_ids)
            conn.execute(f"DELETE FROM document_chunks WHERE qdrant_point_id IN ({placeholders})", tuple(removed_ids))
        for doc_id in doc_metadata:
            count = conn.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (doc_id,)).fetchone()[0]
            conn.execute("UPDATE documents SET chunk_count = ? WHERE id = ?", (count, doc_id))
        conn.commit()

    if not args.skip_qdrant:
        try:
            summary["qdrant"] = update_qdrant(retained_payloads, sorted(removed_ids))
        except RuntimeError as exc:
            summary["qdrant"] = {"error": str(exc)}
    else:
        summary["qdrant"] = "skipped_by_flag"
    summary["backup_db_path"] = str(backup_path)
    write_json(reports / "retained_chunk_cleanup_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
