"""Qdrant embedding service for semantic dentist search."""

from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient, models
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Dentist
from app.services.embeddings import get_embedding_model

logger = logging.getLogger(__name__)


class DentistEmbeddingService:
    """Index dentist profiles in Qdrant for semantic search."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.collection = self.settings.scraper_dentist_qdrant_collection
        self.dimension = self.settings.embedding_dimension
        self.embedding_model = get_embedding_model()

    def _get_client(self) -> QdrantClient:
        from app.services.vector_store import get_qdrant_client
        return get_qdrant_client()

    def ensure_collection(self) -> None:
        client = self._get_client()
        collections = client.get_collections().collections
        names = [c.name for c in collections]

        if self.collection not in names:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", self.collection)

    def _build_text(self, d: Dentist) -> str:
        parts = [
            d.full_name or "",
            d.biography or "",
            d.specialization.value.replace("_", " ") if d.specialization else "",
            d.qualification or "",
            d.clinical_interests or "",
            d.research_interests or "",
        ]
        return " ".join(p for p in parts if p)

    def _build_payload(self, d: Dentist) -> dict:
        return {
            "dentist_id": d.id,
            "name": d.full_name,
            "specialty": d.specialization.value.replace("_", " ") if d.specialization else "",
            "clinic": d.clinic_name or "",
            "experience": d.experience_years or 0,
            "image": d.image_url or d.profile_picture or "",
            "profile_url": d.profile_url or "",
            "qualifications": d.qualification or "",
            "gender": d.gender or "",
            "languages": d.languages or "",
            "department": d.department or "",
            "hospital": d.hospital or "",
        }

    def index_dentist(self, dentist: Dentist) -> str | None:
        client = self._get_client()
        text = self._build_text(dentist)
        if not text.strip():
            return None

        try:
            embedding = self.embedding_model.encode(text).tolist()
        except Exception as exc:
            logger.error("Failed to generate embedding for %s: %s", dentist.full_name, exc)
            return None

        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, dentist.profile_url or dentist.id))
        payload = self._build_payload(dentist)

        try:
            client.upsert(
                collection_name=self.collection,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload,
                    )
                ],
            )
            return point_id
        except Exception as exc:
            logger.error("Failed to index dentist %s: %s", dentist.full_name, exc)
            return None

    def index_all(self) -> dict[str, int]:
        self.ensure_collection()
        dentists = self.db.query(Dentist).filter(Dentist.is_active.is_(True)).all()
        indexed = 0
        failed = 0

        for d in dentists:
            result = self.index_dentist(d)
            if result:
                indexed += 1
            else:
                failed += 1

        logger.info("Indexed %d dentists, %d failed", indexed, failed)
        return {"indexed": indexed, "failed": failed, "total": len(dentists)}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        client = self._get_client()
        try:
            embedding = self.embedding_model.encode(query).tolist()
        except Exception as exc:
            logger.error("Failed to encode search query: %s", exc)
            return []

        try:
            results = client.search(
                collection_name=self.collection,
                query_vector=embedding,
                limit=limit,
            )
            return [
                {
                    "score": hit.score,
                    **(hit.payload or {}),
                }
                for hit in results
            ]
        except Exception as exc:
            logger.error("Qdrant search failed: %s", exc)
            return []

    def reindex(self) -> dict[str, int]:
        client = self._get_client()
        try:
            client.delete_collection(self.collection)
        except Exception:
            pass
        return self.index_all()
