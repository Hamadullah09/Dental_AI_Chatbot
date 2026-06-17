import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.chunk_quality import assess_chunk_quality  # noqa: E402
from app.services.vector_store import get_qdrant_client  # noqa: E402


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export clean non-noisy Dental AI chunks from Qdrant.")
    parser.add_argument("--output", default="chunks.jsonl")
    parser.add_argument("--min-quality", type=float, default=0.6)
    parser.add_argument("--include-noisy", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    written = 0
    with Path(args.output).open("w", encoding="utf-8") as output:
        for point_id, payload in iter_qdrant_payloads(limit=args.limit):
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
