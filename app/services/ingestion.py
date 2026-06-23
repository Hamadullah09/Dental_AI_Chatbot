import re
import uuid
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Callable

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentIngestionLog, DocumentStatus
from app.services.chunk_quality import assess_chunk_quality
from app.services.embeddings import get_embedding_model
from app.services.vector_store import get_qdrant_client


@dataclass
class ParsedChunk:
    text: str
    page_number: int
    chunk_index: int


@dataclass
class ParsedDocument:
    chunks: list[ParsedChunk]
    pages_total: int
    ocr_used: bool = False
    ocr_attempted_pages: int = 0


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

    def add_log(self, db: Session, document: Document, message: str, level: str = "info") -> None:
        db.add(DocumentIngestionLog(document_id=document.id, level=level, message=message))
        db.commit()

    def set_progress(
        self,
        db: Session,
        document: Document,
        progress: int,
        step: str,
        *,
        log_message: str | None = None,
        level: str = "info",
    ) -> None:
        document.ingestion_progress = max(0, min(progress, 100))
        document.ingestion_step = step
        if log_message:
            db.add(DocumentIngestionLog(document_id=document.id, level=level, message=log_message))
        db.commit()

    def parse_pdf(self, pdf_path: Path, log: Callable[[str, str], None] | None = None) -> ParsedDocument:
        reader = PdfReader(str(pdf_path))
        chunks: list[ParsedChunk] = []
        chunk_index = 0
        ocr_used = False
        ocr_attempted_pages = 0
        for page_index, page in enumerate(reader.pages, start=1):
            try:
                raw_text = page.extract_text() or ""
            except Exception:
                raw_text = ""
            page_text = clean_pdf_text(raw_text)
            if not page_text:
                ocr_attempted_pages += 1
                if log:
                    log(f"Page {page_index}: no extractable text found, trying OCR fallback.", "warning")
                ocr_text = extract_page_text_with_ocr(pdf_path, page_index, log)
                if ocr_text:
                    ocr_used = True
                    page_text = clean_pdf_text(ocr_text)
            if not page_text:
                continue
            for chunk_text in split_text(page_text, self.settings.chunk_size, self.settings.chunk_overlap):
                chunks.append(
                    ParsedChunk(text=chunk_text, page_number=page_index, chunk_index=chunk_index)
                )
                chunk_index += 1
        return ParsedDocument(
            chunks=chunks,
            pages_total=len(reader.pages),
            ocr_used=ocr_used,
            ocr_attempted_pages=ocr_attempted_pages,
        )

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
        document.ingestion_progress = 0
        document.ingestion_step = "Queued"
        document.ocr_used = False
        document.ingestion_started_at = datetime.utcnow()
        document.ingestion_completed_at = None
        db.commit()

        try:
            self.set_progress(db, document, 5, "Starting", log_message="Ingestion job started.")
            self.ensure_collection()
            self.set_progress(db, document, 15, "Reading PDF", log_message="Vector collection is ready.")

            def log_parse_event(message: str, level: str = "info") -> None:
                self.add_log(db, document, message, level)

            parsed = self.parse_pdf(Path(document.storage_path), log=log_parse_event)
            chunks = parsed.chunks
            document.ocr_used = parsed.ocr_used
            self.set_progress(
                db,
                document,
                45,
                "Chunking text",
                log_message=(
                    f"Parsed {parsed.pages_total} pages into {len(chunks)} chunks."
                    + (f" OCR was used on scanned pages." if parsed.ocr_used else "")
                ),
            )
            if not chunks:
                raise ValueError(
                    "No extractable text was found in this PDF. If this is a scanned PDF, install OCR support "
                    "(Tesseract, Poppler, pytesseract, and pdf2image) and re-ingest it."
                )

            self.set_progress(db, document, 60, "Creating embeddings", log_message=f"Creating embeddings for {len(chunks)} chunks.")
            vectors = self.embedding_model.encode([chunk.text for chunk in chunks])
            points: list[qmodels.PointStruct] = []

            self.set_progress(db, document, 72, "Replacing old chunks", log_message="Removing previous chunks and vector points for this document.")
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            self.delete_document_vectors(document.id)

            for chunk, vector in zip(chunks, vectors):
                point_id = str(uuid.uuid4())
                quality = assess_chunk_quality(chunk.text)
                payload = {
                    "chunk_id": point_id,
                    "text": chunk.text,
                    "document_id": document.id,
                    "document_name": document.original_filename,
                    "book_title": document.title or document.original_filename,
                    "title": document.title or document.original_filename,
                    "author_or_source": document.author_or_source,
                    "edition": document.edition,
                    "year": document.publication_year,
                    "document_type": document.document_type.value,
                    "trust_level": document.trust_level.value,
                    "review_status": document.review_status.value,
                    "specialty": document.specialty,
                    "language": document.language,
                    "file_hash": document.file_hash,
                    "source": document.original_filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "quality_score": quality.quality_score,
                    "is_noisy": quality.is_noisy,
                    "noise_reasons": quality.noise_reasons,
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
                        quality_score=quality.quality_score,
                        is_noisy=quality.is_noisy,
                        noise_reasons=json.dumps(quality.noise_reasons),
                    )
                )

            self.set_progress(db, document, 88, "Writing vector index", log_message=f"Writing {len(points)} chunks to the vector store.")
            self.qdrant.upsert(collection_name=self.settings.qdrant_collection, points=points)
            document.status = DocumentStatus.ready
            document.chunk_count = len(points)
            document.ingestion_progress = 100
            document.ingestion_step = "Ready"
            document.ingestion_completed_at = datetime.utcnow()
            db.add(DocumentIngestionLog(document_id=document.id, level="info", message=f"Ingestion completed with {len(points)} chunks."))
            db.commit()
            return len(points)
        except Exception as exc:
            document.status = DocumentStatus.failed
            document.error_message = str(exc)
            document.ingestion_step = "Failed"
            document.ingestion_completed_at = datetime.utcnow()
            db.add(DocumentIngestionLog(document_id=document.id, level="error", message=f"Ingestion failed: {exc}"))
            db.commit()
            raise


def clean_pdf_text(raw_text: str) -> str:
    text = raw_text.replace("\x00", " ")
    text = re.sub(r"/H17040|H17040", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBM\.indd\b.*?(?=\s|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPlate\s+[A-Za-z0-9.-]+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(clean_pdf_line(line) for line in text.splitlines())
    text = "\n".join(line for line in text.splitlines() if line.strip())
    return " ".join(text.split())


def clean_pdf_line(line: str) -> str:
    stripped = line.strip()
    lower = stripped.lower()
    if not stripped:
        return ""
    noisy_phrases = [
        "put a tick",
        "put a cross",
        "tick/cross",
        "how often do you clean your teeth",
        "never fairly often very often",
        "don't know",
        "don’t know",
    ]
    if any(phrase in lower for phrase in noisy_phrases):
        return ""
    if re.fullmatch(r"[\W\d_]{4,}", stripped):
        return ""
    if len(stripped) < 4 and not re.search(r"[a-zA-Z]{3,}", stripped):
        return ""
    return stripped


def extract_page_text_with_ocr(
    pdf_path: Path,
    page_number: int,
    log: Callable[[str, str], None] | None = None,
) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        if log:
            log("OCR packages are not installed. Install pdf2image and pytesseract to process scanned PDFs.", "warning")
        return ""

    try:
        images = convert_from_path(
            str(pdf_path),
            first_page=page_number,
            last_page=page_number,
            dpi=200,
            fmt="png",
            thread_count=1,
        )
        if not images:
            return ""
        text = pytesseract.image_to_string(images[0]) or ""
        if text.strip() and log:
            log(f"Page {page_number}: OCR extracted text successfully.", "info")
        return text
    except Exception as exc:
        if log:
            log(f"Page {page_number}: OCR failed ({exc}).", "warning")
        return ""


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
