import uuid
from dataclasses import dataclass
from pathlib import Path

from langchain.text_splitter import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentStatus


@dataclass
class ParsedChunk:
    text: str
    page_number: int
    chunk_index: int


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = SentenceTransformer(self.settings.embedding_model_name)
        self.qdrant = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key)

    @property
    def vector_size(self) -> int:
        return int(self.embedding_model.get_sentence_embedding_dimension())

    def ensure_collection(self) -> None:
        collections = self.qdrant.get_collections().collections
        if any(collection.name == self.settings.qdrant_collection for collection in collections):
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
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

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
            for chunk_text in splitter.split_text(page_text):
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
