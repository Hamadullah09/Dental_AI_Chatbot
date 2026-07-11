from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client import models as qmodels

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.models import Document, DocumentChunk, DocumentStatus, DocumentVisual
from app.services.chunk_quality import assess_chunk_quality
from app.services.embeddings import get_embedding_model
from app.services.ingestion import stable_content_hash
from app.services.vector_store import get_qdrant_client


REPORT_DIR = Path("cleanup_reports")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a new clean Qdrant collection from reviewed, non-noisy DB chunks. "
            "Dry-run by default. The current production collection is never overwritten."
        )
    )
    parser.add_argument("--target-collection", default="dental_docs_clean", help="New clean Qdrant collection name.")
    parser.add_argument("--apply", action="store_true", help="Create/upsert the target clean collection.")
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Delete and recreate the target collection first. Refuses to run if target is the production collection.",
    )
    parser.add_argument("--min-quality", type=float, default=0.6)
    parser.add_argument("--trust-level", action="append", default=["high", "medium"])
    parser.add_argument("--review-status", action="append", default=["approved", "reviewed"])
    parser.add_argument("--include-visuals", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    settings = get_settings()
    if args.target_collection == settings.qdrant_collection:
        raise SystemExit(
            f"Refusing to rebuild into the active collection '{settings.qdrant_collection}'. "
            "Choose a separate target collection."
        )

    init_db()
    retained_docs, retained_chunks, retained_visuals, skipped = collect_clean_records(
        min_quality=args.min_quality,
        trust_levels=set(args.trust_level),
        review_statuses=set(args.review_status),
        include_visuals=args.include_visuals,
    )
    summary: dict[str, Any] = {
        "target_collection": args.target_collection,
        "current_collection_preserved": settings.qdrant_collection,
        "apply": args.apply,
        "replace_target": args.replace_target,
        "filters": {
            "min_quality": args.min_quality,
            "trust_levels": args.trust_level,
            "review_statuses": args.review_status,
            "include_visuals": args.include_visuals,
        },
        "retained_documents": len(retained_docs),
        "retained_document_samples": [
            {
                "document_id": document.id,
                "title": document.canonical_title or document.title or document.original_filename,
                "filename": document.original_filename,
                "trust_level": enum_value(document.trust_level),
                "review_status": enum_value(document.review_status),
            }
            for document in retained_docs[:20]
        ],
        "retained_text_chunks": len(retained_chunks),
        "retained_visuals": len(retained_visuals),
        "skipped": skipped,
    }

    if args.apply:
        qdrant_summary = rebuild_collection(
            target_collection=args.target_collection,
            chunks=retained_chunks,
            visuals=retained_visuals,
            replace_target=args.replace_target,
            batch_size=max(1, args.batch_size),
        )
        summary["qdrant"] = qdrant_summary
    else:
        summary["qdrant"] = "dry_run_only"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "rebuild_clean_qdrant_plan.json"
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Report written to: {report_path}")


def collect_clean_records(
    min_quality: float,
    trust_levels: set[str],
    review_statuses: set[str],
    include_visuals: bool,
) -> tuple[list[Document], list[tuple[DocumentChunk, Document]], list[DocumentVisual], dict[str, int]]:
    db = SessionLocal()
    skipped = {
        "duplicate_documents": 0,
        "duplicate_chunks": 0,
        "noisy_or_low_quality_chunks": 0,
        "untrusted_documents": 0,
        "unreviewed_documents": 0,
        "visuals_deduped_or_low_quality": 0,
    }
    try:
        documents = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.ready)
            .order_by(Document.created_at.asc())
            .all()
        )
        selected_docs: list[Document] = []
        seen_doc_hashes: set[str] = set()

        for document in documents:
            trust_level = enum_value(document.trust_level)
            review_status = enum_value(document.review_status)
            if trust_level not in trust_levels:
                skipped["untrusted_documents"] += 1
                continue
            if review_status not in review_statuses:
                skipped["unreviewed_documents"] += 1
                continue
            exact_doc_key = document.file_hash or document.content_hash
            if exact_doc_key and exact_doc_key in seen_doc_hashes:
                skipped["duplicate_documents"] += 1
                continue
            if exact_doc_key:
                seen_doc_hashes.add(exact_doc_key)
            selected_docs.append(document)

        selected_doc_ids = {document.id for document in selected_docs}
        chunk_rows = (
            db.query(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(DocumentChunk.document_id.in_(selected_doc_ids))
            .order_by(Document.original_filename.asc(), DocumentChunk.chunk_index.asc())
            .all()
            if selected_doc_ids
            else []
        )
        seen_chunk_hashes: set[str] = set()
        retained_chunks: list[tuple[DocumentChunk, Document]] = []
        for chunk, document in chunk_rows:
            quality = assess_chunk_quality(chunk.text)
            quality_score = float(chunk.quality_score or quality.quality_score or 0.0)
            is_noisy = bool(chunk.is_noisy or quality.is_noisy)
            content_hash = chunk.content_hash or stable_content_hash(chunk.text)
            if is_noisy or quality_score < min_quality:
                skipped["noisy_or_low_quality_chunks"] += 1
                continue
            if content_hash in seen_chunk_hashes:
                skipped["duplicate_chunks"] += 1
                continue
            seen_chunk_hashes.add(content_hash)
            retained_chunks.append((chunk, document))

        retained_visuals: list[DocumentVisual] = []
        if include_visuals and selected_doc_ids:
            visual_rows = (
                db.query(DocumentVisual)
                .filter(DocumentVisual.document_id.in_(selected_doc_ids))
                .order_by(DocumentVisual.document_name.asc(), DocumentVisual.page_number.asc())
                .all()
            )
            seen_visual_hashes: set[str] = set()
            for visual in visual_rows:
                key = visual.content_hash or f"{visual.document_id}:{visual.page_number}:{visual.image_path}"
                if key in seen_visual_hashes or float(visual.quality_score or 0.0) < 0.45:
                    skipped["visuals_deduped_or_low_quality"] += 1
                    continue
                seen_visual_hashes.add(key)
                retained_visuals.append(visual)

        return selected_docs, retained_chunks, retained_visuals, skipped
    finally:
        db.close()


def rebuild_collection(
    target_collection: str,
    chunks: list[tuple[DocumentChunk, Document]],
    visuals: list[DocumentVisual],
    replace_target: bool,
    batch_size: int,
) -> dict[str, Any]:
    qdrant = get_qdrant_client()
    embedding_model = get_embedding_model()
    vector_size = int(embedding_model.get_sentence_embedding_dimension() or 384)

    ensure_collection(qdrant, target_collection, vector_size, replace_target=replace_target)

    text_points = build_text_points(chunks, embedding_model, batch_size=batch_size)
    visual_points = build_visual_points(visuals, embedding_model, batch_size=batch_size)
    upsert_batches(qdrant, target_collection, text_points, batch_size=batch_size)
    upsert_batches(qdrant, target_collection, visual_points, batch_size=batch_size)
    return {
        "collection": target_collection,
        "vector_size": vector_size,
        "text_points_upserted": len(text_points),
        "visual_points_upserted": len(visual_points),
    }


def ensure_collection(qdrant, collection: str, vector_size: int, replace_target: bool) -> None:
    exists = collection_exists(qdrant, collection)
    if exists and replace_target:
        qdrant.delete_collection(collection_name=collection)
        exists = False
    if exists:
        return
    qdrant.create_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )


def collection_exists(qdrant, collection: str) -> bool:
    if hasattr(qdrant, "collection_exists"):
        return bool(qdrant.collection_exists(collection_name=collection))
    try:
        qdrant.get_collection(collection_name=collection)
        return True
    except Exception:
        return False


def build_text_points(
    chunks: list[tuple[DocumentChunk, Document]],
    embedding_model,
    batch_size: int,
) -> list[qmodels.PointStruct]:
    points: list[qmodels.PointStruct] = []
    for batch in batched(chunks, batch_size):
        texts = [chunk.text for chunk, _ in batch]
        vectors = embedding_model.encode(texts)
        for (chunk, document), vector in zip(batch, vectors):
            point_id = chunk.qdrant_point_id or str(uuid.uuid4())
            payload = text_payload(chunk, document, point_id)
            points.append(qmodels.PointStruct(id=point_id, vector=vector_to_list(vector), payload=payload))
    return points


def build_visual_points(
    visuals: list[DocumentVisual],
    embedding_model,
    batch_size: int,
) -> list[qmodels.PointStruct]:
    points: list[qmodels.PointStruct] = []
    for batch in batched(visuals, batch_size):
        texts = [visual_searchable_text(row) for row in batch]
        vectors = embedding_model.encode(texts)
        for visual, vector in zip(batch, vectors):
            point_id = visual.qdrant_point_id or str(uuid.uuid4())
            payload = visual_payload(visual, point_id)
            points.append(qmodels.PointStruct(id=point_id, vector=vector_to_list(vector), payload=payload))
    return points


def text_payload(chunk: DocumentChunk, document: Document, point_id: str) -> dict[str, Any]:
    title = document.canonical_title or document.title or document.original_filename
    return {
        "payload_type": "text",
        "chunk_id": point_id,
        "qdrant_point_id": point_id,
        "text": chunk.text,
        "document_id": document.id,
        "document_name": document.original_filename,
        "canonical_document_title": title,
        "book_title": title,
        "title": title,
        "author_or_source": document.author_or_source or document.author,
        "publisher": document.publisher,
        "edition": document.edition,
        "year": document.publication_year,
        "document_type": enum_value(document.document_type),
        "trust_level": chunk.trust_level or enum_value(document.trust_level),
        "review_status": chunk.review_status or enum_value(document.review_status),
        "specialty": chunk.dental_specialty or document.dental_specialty or document.specialty,
        "dental_specialty": chunk.dental_specialty or document.dental_specialty or document.specialty,
        "topic": chunk.topic or document.topic,
        "difficulty_level": chunk.difficulty_level or document.difficulty_level,
        "language": chunk.language or document.language,
        "file_hash": document.file_hash,
        "content_hash": chunk.content_hash or stable_content_hash(chunk.text),
        "section_title": chunk.section_title,
        "chapter_title": chunk.chapter_title,
        "source": document.original_filename,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "quality_score": float(chunk.quality_score or 0.0),
        "is_noisy": bool(chunk.is_noisy),
        "noise_reasons": chunk.noise_reasons,
    }


def visual_payload(visual: DocumentVisual, point_id: str) -> dict[str, Any]:
    return {
        "payload_type": "visual",
        "visual_id": visual.visual_id,
        "qdrant_point_id": point_id,
        "document_id": visual.document_id,
        "document_name": visual.document_name,
        "book_title": visual.document_name,
        "title": visual.document_name,
        "page_number": visual.page_number,
        "visual_type": visual.visual_type,
        "image_path": visual.image_path,
        "image_url": image_url_for_path(visual.image_path),
        "caption_text": visual.caption_text,
        "nearby_text": visual.nearby_text,
        "generated_description": visual.generated_description,
        "related_chunk_ids": parse_json_list(visual.related_chunk_ids),
        "quality_score": float(visual.quality_score or 0.0),
        "review_status": visual.review_status,
        "content_hash": visual.content_hash,
        "text": visual_searchable_text(visual),
    }


def visual_searchable_text(visual: DocumentVisual) -> str:
    return " ".join(
        part.strip()
        for part in [
            visual.caption_text or "",
            visual.nearby_text or "",
            visual.generated_description or "",
            visual.document_name or "",
            visual.visual_type or "",
        ]
        if part and part.strip()
    )


def upsert_batches(qdrant, collection: str, points: list[qmodels.PointStruct], batch_size: int) -> None:
    for batch in batched(points, batch_size):
        qdrant.upsert(collection_name=collection, points=list(batch))


def batched(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def vector_to_list(vector) -> list[float]:
    return vector.tolist() if hasattr(vector, "tolist") else list(vector)


def enum_value(value) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if item]
    return []


def image_url_for_path(image_path: str) -> str:
    normalized = (image_path or "").replace("\\", "/")
    marker = "uploads/"
    index = normalized.find(marker)
    if index >= 0:
        return "/" + normalized[index:]
    return "/" + normalized.lstrip("/")


if __name__ == "__main__":
    main()
