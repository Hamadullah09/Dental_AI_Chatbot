import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Document, DocumentChunk  # noqa: E402
from app.services.chunk_quality import assess_chunk_quality  # noqa: E402
from app.services.vector_store import get_qdrant_client  # noqa: E402


def chunk_payload_from_db(chunk: DocumentChunk, document: Document) -> tuple[str, dict]:
    return chunk.qdrant_point_id, {
        "chunk_id": chunk.qdrant_point_id,
        "document_id": document.id,
        "document_name": document.original_filename,
        "book_title": document.title,
        "title": document.title,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "quality_score": chunk.quality_score,
        "is_noisy": chunk.is_noisy,
        "noise_reasons": json.loads(chunk.noise_reasons) if chunk.noise_reasons else [],
        "review_status": document.review_status.value,
        "document_type": document.document_type.value,
        "trust_level": document.trust_level.value,
    }


def iter_db_payloads(limit: int | None = None):
    emitted = 0
    with SessionLocal() as db:
        query = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .order_by(Document.created_at.desc(), DocumentChunk.chunk_index.asc())
        )
        for chunk, document in query.yield_per(250):
            yield chunk_payload_from_db(chunk, document)
            emitted += 1
            if limit and emitted >= limit:
                return


def iter_qdrant_payloads(limit: int | None = None):
    settings = get_settings()
    qdrant = get_qdrant_client()
    offset = None
    emitted = 0
    while True:
        records, offset = qdrant.scroll(
            collection_name=settings.qdrant_collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            break
        for record in records:
            yield str(record.id), record.payload or {}
            emitted += 1
            if limit and emitted >= limit:
                return
        if offset is None:
            break


def iter_payloads(source: str, limit: int | None = None):
    if source == "db":
        yield from iter_db_payloads(limit=limit)
        return
    if source == "qdrant":
        yield from iter_qdrant_payloads(limit=limit)
        return
    try:
        yield from iter_qdrant_payloads(limit=limit)
    except RuntimeError as exc:
        if "already accessed by another instance" not in str(exc):
            raise
        print("Qdrant local storage is locked by another process. Falling back to SQL database chunks.")
        yield from iter_db_payloads(limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export clean non-noisy Dental AI chunks from Qdrant.")
    parser.add_argument("--output", default="chunks.jsonl")
    parser.add_argument("--min-quality", type=float, default=0.6)
    parser.add_argument("--include-noisy", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source", choices=["auto", "qdrant", "db"], default="auto")
    args = parser.parse_args()

    written = 0
    with Path(args.output).open("w", encoding="utf-8") as output:
        for point_id, payload in iter_payloads(source=args.source, limit=args.limit):
            text = str(payload.get("text") or "").strip()
            quality = assess_chunk_quality(text)
            quality_score = float(payload.get("quality_score", quality.quality_score) or 0.0)
            is_noisy = bool(payload.get("is_noisy", quality.is_noisy))
            if not args.include_noisy and (is_noisy or quality_score < args.min_quality):
                continue
            row = {
                "chunk_id": payload.get("chunk_id") or point_id,
                "document_id": payload.get("document_id"),
                "document_name": payload.get("book_title") or payload.get("title") or payload.get("document_name") or payload.get("source"),
                "page_number": payload.get("page_number"),
                "chunk_index": payload.get("chunk_index"),
                "text": text,
                "quality_score": round(quality_score, 3),
                "is_noisy": is_noisy,
                "noise_reasons": payload.get("noise_reasons") or quality.noise_reasons,
                "review_status": payload.get("review_status"),
                "document_type": payload.get("document_type"),
                "trust_level": payload.get("trust_level"),
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    print(f"Exported {written} chunks to {args.output}")


if __name__ == "__main__":
    main()
