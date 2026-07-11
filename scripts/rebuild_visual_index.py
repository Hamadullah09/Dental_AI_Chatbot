from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.models import DocumentVisual
from app.services.embeddings import get_embedding_model
from app.services.vector_store import ensure_qdrant_collection, get_qdrant_client
from app.services.visuals import image_url_for_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Qdrant vectors for existing document_visuals rows.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of visuals.")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    embedding_model = get_embedding_model()
    qdrant = get_qdrant_client()
    vector_size = int(embedding_model.get_sentence_embedding_dimension() or 384)
    ensure_qdrant_collection(qdrant, settings.qdrant_collection, vector_size)
    with SessionLocal() as db:
        visuals = db.query(DocumentVisual).order_by(DocumentVisual.created_at.desc()).all()
        if args.limit:
            visuals = visuals[: args.limit]
        if not visuals:
            print("No visual records found.")
            return
        texts = [searchable_text(visual) for visual in visuals]
        vectors = embedding_model.encode(texts)
        points: list[qmodels.PointStruct] = []
        for visual, vector in zip(visuals, vectors):
            point_id = visual.qdrant_point_id or visual.visual_id
            visual.qdrant_point_id = point_id
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload=payload_for_visual(visual, point_id),
                )
            )
        batch_size = max(1, settings.vector_upsert_batch_size)
        for start in range(0, len(points), batch_size):
            qdrant.upsert(collection_name=settings.qdrant_collection, points=points[start : start + batch_size])
        db.commit()
    print(f"Rebuilt visual index for {len(visuals)} visuals.")


def searchable_text(visual: DocumentVisual) -> str:
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


def payload_for_visual(visual: DocumentVisual, point_id: str) -> dict:
    related = []
    if visual.related_chunk_ids:
        try:
            related = json.loads(visual.related_chunk_ids)
        except json.JSONDecodeError:
            related = []
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
        "related_chunk_ids": related,
        "quality_score": visual.quality_score,
        "review_status": visual.review_status,
        "content_hash": visual.content_hash,
        "text": searchable_text(visual),
    }


if __name__ == "__main__":
    main()
