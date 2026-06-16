import uuid
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.embeddings import get_embedding_model
from app.services.vector_store import get_qdrant_client


@dataclass
class ParsedChunk:
    text: str
    page_number: int
    chunk_index: int


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = get_embedding_model()
        self.qdrant = get_qdrant_client()

    @property
    def vector_size(self) -> int:
        return int(self.embedding_model.get_sentence_embedding_dimension())

    def ensure_collection(self) -> None:
        collections = self.qdrant.get_collections().collections
        existing = next((collection for collection in collections if collection.name == self.settings.qdrant_collection), None)
        if existing:
            return
        self.qdrant.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def recreate_collection(self) -> None:
        self.qdrant.recreate_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def parse_pdf(self, pdf_path: Path) -> list[ParsedChunk]:
        reader = PdfReader(str(pdf_path))
        chunks: list[ParsedChunk] = []
        chunk_index = 0
        for page_index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            page_text = " ".join(page_text.split())
            if not page_text:
                continue
            for chunk_text in split_text(page_text, self.settings.chunk_size, self.settings.chunk_overlap):
                chunks.append(
                    ParsedChunk(text=chunk_text, page_number=page_index, chunk_index=chunk_index)
                )
                chunk_index += 1
        return chunks

    def delete_document_vectors(self, document_id: str) -> None:
        self.ensure_collection()
        self.qdrant.delete(
            collection_name=self.settings.qdrant_collection,
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

    def ingest_document(self, db: Session, document: Document) -> int:
        document.status = DocumentStatus.processing
        document.error_message = None
        db.commit()

        try:
            self.ensure_collection()
            chunks = self.parse_pdf(Path(document.storage_path))
            if not chunks:
                raise ValueError("No extractable text was found in this PDF.")

            vectors = self.embedding_model.encode([chunk.text for chunk in chunks])
            points: list[qmodels.PointStruct] = []

            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            self.delete_document_vectors(document.id)

            for chunk, vector in zip(chunks, vectors):
                point_id = str(uuid.uuid4())
                payload = {
                    "text": chunk.text,
                    "document_id": document.id,
                    "document_name": document.original_filename,
                    "source": document.original_filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                points.append(qmodels.PointStruct(id=point_id, vector=vector.tolist(), payload=payload))
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        qdrant_point_id=point_id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        text=chunk.text,
                        token_estimate=max(1, len(chunk.text.split())),
                    )
                )

            self.qdrant.upsert(collection_name=self.settings.qdrant_collection, points=points)
            document.status = DocumentStatus.ready
            document.chunk_count = len(points)
            db.commit()
            return len(points)
        except Exception as exc:
            document.status = DocumentStatus.failed
            document.error_message = str(exc)
            db.commit()
            raise


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            split_at = max(text.rfind(". ", start, end), text.rfind(" ", start, end))
            if split_at > start + int(chunk_size * 0.5):
                end = split_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
