import re
import uuid
import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Callable
import time

import numpy as np
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentIngestionLog, DocumentStatus
from app.services.chunk_quality import assess_chunk_quality
from app.services.embeddings import get_embedding_model
from app.services.vector_store import ensure_qdrant_collection, get_qdrant_client
from app.services.visuals import extract_and_index_document_visuals


@dataclass
class ParsedChunk:
    text: str
    page_number: int
    chunk_index: int
    section_title: str = ""
    chapter_title: str = ""


@dataclass
class ParsedDocument:
    chunks: list[ParsedChunk]
    pages_total: int
    ocr_used: bool = False
    ocr_attempted_pages: int = 0

    def __len__(self) -> int:
        return len(self.chunks)

    def __iter__(self):
        return iter(self.chunks)

    def __getitem__(self, index):
        return self.chunks[index]


class IngestionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = get_embedding_model()
        self.qdrant = get_qdrant_client()

    @property
    def vector_size(self) -> int:
        return int(self.embedding_model.get_sentence_embedding_dimension())

    def ensure_collection(self) -> None:
        ensure_qdrant_collection(
            self.qdrant,
            collection_name=self.settings.qdrant_collection,
            vector_size=self.vector_size,
            replace_if_wrong_size=True,
        )

    def collection_vector_size_matches(self) -> bool:
        try:
            info = self.qdrant.get_collection(self.settings.qdrant_collection)
            vectors = info.config.params.vectors
            size = getattr(vectors, "size", None)
            return int(size or 0) == self.vector_size
        except Exception:
            return False

    def recreate_collection(self) -> None:
        self.qdrant.recreate_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def add_log(self, db: Session, document: Document, message: str, level: str = "info") -> None:
        db.add(DocumentIngestionLog(document_id=document.id, level=level, message=message))
        commit_with_retry(db)

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
        commit_with_retry(db)

    def parse_pdf(self, pdf_path: Path, log: Callable[[str, str], None] | None = None) -> ParsedDocument:
        extracted_pages: list[tuple[int, str]] = []
        with pdf_path.open("rb") as pdf_stream:
            reader = PdfReader(pdf_stream)
            pages_total = len(reader.pages)
            for page_index, page in enumerate(reader.pages, start=1):
                try:
                    raw_text = page.extract_text() or ""
                except Exception:
                    raw_text = ""
                extracted_pages.append((page_index, raw_text))

        repeated_lines = detect_repeated_page_lines([text for _, text in extracted_pages])
        chunks: list[ParsedChunk] = []
        chunk_index = 0
        ocr_used = False
        ocr_attempted_pages = 0
        for page_index, raw_text in extracted_pages:
            page_text = clean_pdf_text(raw_text, repeated_lines=repeated_lines)
            if not page_text:
                ocr_attempted_pages += 1
                if log:
                    log(f"Page {page_index}: no extractable text found, trying OCR fallback.", "warning")
                ocr_text = extract_page_text_with_ocr(pdf_path, page_index, log)
                if ocr_text:
                    ocr_used = True
                    page_text = clean_pdf_text(ocr_text, repeated_lines=repeated_lines)
            if not page_text:
                continue
            if is_low_value_page(page_text):
                if log:
                    log(f"Page {page_index}: skipped low-value page text (TOC, references, form, or OCR/layout noise).", "info")
                continue
            for section in split_into_sections(page_text):
                for chunk_text in split_section_text(section["text"], self.settings.chunk_size, self.settings.chunk_overlap):
                    chunks.append(
                        ParsedChunk(
                            text=chunk_text,
                            page_number=page_index,
                            chunk_index=chunk_index,
                            section_title=section.get("section_title", ""),
                            chapter_title=section.get("chapter_title", ""),
                        )
                    )
                    chunk_index += 1
        return ParsedDocument(
            chunks=chunks,
            pages_total=pages_total,
            ocr_used=ocr_used,
            ocr_attempted_pages=ocr_attempted_pages,
        )

    def delete_document_vectors(self, document_id: str, log: Callable[[str, str], None] | None = None) -> None:
        self.ensure_collection()
        try:
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
        except Exception as exc:
            if is_qdrant_collection_missing_error(exc):
                if log:
                    log("Vector collection was missing during cleanup; recreating it and continuing.", "warning")
                self.ensure_collection()
                return
            if is_local_qdrant_storage_error(exc):
                if log:
                    log(
                        "Vector store cleanup failed because local Qdrant storage appears inconsistent. "
                        "Recreating the local vector collection and continuing ingestion.",
                        "warning",
                    )
                self.recreate_collection()
                return
            raise

    def encode_chunks(self, chunks: list[ParsedChunk]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = max(1, int(self.settings.embedding_batch_size))
        expected_size = self.vector_size
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            encoded = self.embedding_model.encode([chunk.text for chunk in batch])
            encoded_array = np.asarray(encoded, dtype=np.float32)
            if encoded_array.ndim != 2:
                raise ValueError(f"Embedding model returned invalid shape {encoded_array.shape}.")
            if encoded_array.shape[1] != expected_size:
                raise ValueError(
                    f"Embedding dimension mismatch: model returned {encoded_array.shape[1]}, "
                    f"but vector collection expects {expected_size}."
                )
            vectors.extend(vector.tolist() for vector in encoded_array)
        if len(vectors) != len(chunks):
            raise ValueError(f"Embedding count mismatch: created {len(vectors)} vectors for {len(chunks)} chunks.")
        return vectors

    def upsert_points_in_batches(self, points: list[qmodels.PointStruct], log: Callable[[str, str], None] | None = None) -> None:
        batch_size = max(1, int(self.settings.vector_upsert_batch_size))
        for start in range(0, len(points), batch_size):
            batch = points[start:start + batch_size]
            for attempt in range(3):
                try:
                    self.qdrant.upsert(collection_name=self.settings.qdrant_collection, points=batch)
                    break
                except Exception as exc:
                    if is_qdrant_collection_missing_error(exc):
                        if log:
                            log("Vector collection was missing during upsert; recreating it and retrying.", "warning")
                        self.ensure_collection()
                        if attempt < 2:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                    if not is_local_qdrant_storage_error(exc) or attempt == 2:
                        raise
                    if log:
                        log(
                            f"Vector batch {start + 1}-{start + len(batch)} hit local storage transaction contention; retrying.",
                            "warning",
                        )
                    time.sleep(0.5 * (attempt + 1))

    def ingest_document(self, db: Session, document: Document) -> int:
        started_monotonic = time.monotonic()

        def check_timeout(stage: str) -> None:
            timeout_seconds = int(getattr(self.settings, "ingestion_timeout_seconds", 0) or 0)
            if timeout_seconds > 0 and time.monotonic() - started_monotonic > timeout_seconds:
                raise TimeoutError(f"Ingestion timed out during {stage} after {timeout_seconds} seconds.")

        document.status = DocumentStatus.processing
        document.error_message = None
        document.ingestion_progress = 0
        document.ingestion_step = "Queued"
        document.ocr_used = False
        document.ingestion_started_at = datetime.utcnow()
        document.ingestion_completed_at = None
        commit_with_retry(db)

        try:
            self.set_progress(db, document, 5, "Starting", log_message="Ingestion job started.")
            self.ensure_collection()
            self.set_progress(db, document, 15, "Reading PDF", log_message="Vector collection is ready.")

            parse_log_buffer: list[tuple[str, str]] = []

            def log_parse_event(message: str, level: str = "info") -> None:
                parse_log_buffer.append((message, level))

            parsed = self.parse_pdf(Path(document.storage_path), log=log_parse_event)
            check_timeout("PDF parsing")
            chunks = filter_quality_chunks(dedupe_parsed_chunks(parsed.chunks))
            chunks = remove_existing_duplicate_chunks(db, chunks, document.id)
            document.ocr_used = parsed.ocr_used
            document.extraction_method = "ocr" if parsed.ocr_used else "pdf_text"
            document.canonical_title = document.canonical_title or document.title or title_from_filename(document.original_filename)
            document.title = document.title or document.canonical_title
            document.author = document.author or document.author_or_source
            document.dental_specialty = document.dental_specialty or document.specialty or infer_dental_specialty(document.canonical_title or document.original_filename)
            document.specialty = document.specialty or document.dental_specialty
            document.topic = document.topic or infer_chunk_topic(document.canonical_title or document.original_filename, document.dental_specialty or "general_dentistry")
            document.difficulty_level = document.difficulty_level or infer_difficulty_level(document.canonical_title or document.original_filename)
            document.language = document.language or "English"
            document.content_hash = stable_content_hash(" ".join(chunk.text for chunk in chunks[:50]))
            for message, level in parse_log_buffer[-80:]:
                db.add(DocumentIngestionLog(document_id=document.id, level=level, message=message))
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
                ocr_details = ""
                if parsed.ocr_attempted_pages:
                    recent_ocr_logs = [
                        message
                        for message, level in parse_log_buffer[-20:]
                        if "ocr" in message.lower() or level == "warning"
                    ]
                    if recent_ocr_logs:
                        ocr_details = " Last OCR detail: " + recent_ocr_logs[-1]
                raise ValueError(
                    "No extractable text was found in this PDF. If this is a scanned PDF, install OCR support "
                    "(Tesseract, Poppler, pytesseract, and pdf2image) and re-ingest it."
                    + ocr_details
                )

            self.set_progress(db, document, 60, "Creating embeddings", log_message=f"Creating embeddings for {len(chunks)} chunks.")
            vectors = self.encode_chunks(chunks)
            check_timeout("embedding generation")
            points: list[qmodels.PointStruct] = []
            db_chunks: list[DocumentChunk] = []

            self.set_progress(db, document, 72, "Replacing old chunks", log_message="Removing previous chunks and vector points for this document.")
            existing_chunk_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            commit_with_retry(db)
            if existing_chunk_count:
                self.delete_document_vectors(document.id, log=log_parse_event)
            else:
                db.add(
                    DocumentIngestionLog(
                        document_id=document.id,
                        level="info",
                        message="No previous chunks found for this document; skipping old vector cleanup.",
                    )
                )
                commit_with_retry(db)

            for chunk, vector in zip(chunks, vectors):
                point_id = str(uuid.uuid4())
                quality = assess_chunk_quality(chunk.text)
                canonical_title = document.canonical_title or document.title or document.original_filename
                specialty = document.specialty or infer_dental_specialty(canonical_title)
                topic = infer_chunk_topic(f"{canonical_title} {chunk.text[:500]}", specialty)
                difficulty_level = infer_difficulty_level(canonical_title)
                language = document.language or "English"
                chunk_hash = stable_content_hash(chunk.text)
                section_title = chunk.section_title or infer_section_title(chunk.text)
                chapter_title = chunk.chapter_title or ""
                payload = {
                    "payload_type": "text",
                    "chunk_id": point_id,
                    "text": chunk.text,
                    "document_id": document.id,
                    "document_name": document.original_filename,
                    "canonical_document_title": canonical_title,
                    "book_title": canonical_title,
                    "title": canonical_title,
                    "author_or_source": document.author_or_source,
                    "publisher": getattr(document, "publisher", None),
                    "edition": document.edition,
                    "year": document.publication_year,
                    "document_type": document.document_type.value,
                    "trust_level": document.trust_level.value,
                    "review_status": document.review_status.value,
                    "specialty": specialty,
                    "dental_specialty": specialty,
                    "topic": topic,
                    "difficulty_level": difficulty_level,
                    "language": language,
                    "file_hash": document.file_hash,
                    "content_hash": chunk_hash,
                    "section_title": section_title,
                    "chapter_title": chapter_title,
                    "source": document.original_filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "quality_score": quality.quality_score,
                    "is_noisy": quality.is_noisy,
                    "noise_reasons": quality.noise_reasons,
                }
                points.append(qmodels.PointStruct(id=point_id, vector=vector, payload=payload))
                db_chunks.append(
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
                        canonical_document_title=canonical_title,
                        section_title=section_title,
                        chapter_title=chapter_title,
                        dental_specialty=specialty,
                        topic=topic,
                        difficulty_level=difficulty_level,
                        language=language,
                        trust_level=document.trust_level.value,
                        review_status=document.review_status.value,
                        content_hash=chunk_hash,
                    )
                )

            self.set_progress(db, document, 88, "Writing vector index", log_message=f"Writing {len(points)} chunks to the vector store.")
            self.upsert_points_in_batches(points, log=log_parse_event)
            check_timeout("text vector upsert")
            db.bulk_save_objects(db_chunks)
            commit_with_retry(db)
            visual_count = 0
            if self.settings.enable_multimodal_rag:
                self.set_progress(
                    db,
                    document,
                    94,
                    "Extracting visuals",
                    log_message="Extracting page snapshots, embedded images, figure regions, and tables.",
                )
                visual_count = extract_and_index_document_visuals(
                    db,
                    document,
                    embedding_model=self.embedding_model,
                    qdrant=self.qdrant,
                    log=lambda message, level="info": db.add(
                        DocumentIngestionLog(document_id=document.id, level=level, message=message)
                    ),
                )
                check_timeout("visual extraction")
                commit_with_retry(db)
            else:
                db.add(
                    DocumentIngestionLog(
                        document_id=document.id,
                        level="info",
                        message="Multimodal RAG is disabled; skipped visual extraction.",
                    )
                )
                commit_with_retry(db)
            document.status = DocumentStatus.ready
            document.chunk_count = len(points)
            document.ingestion_progress = 100
            document.ingestion_step = "Ready"
            document.ingestion_completed_at = datetime.utcnow()
            db.add(DocumentIngestionLog(document_id=document.id, level="info", message=f"Ingestion completed with {len(points)} chunks and {visual_count} visuals."))
            commit_with_retry(db)
            return len(points)
        except Exception as exc:
            mark_ingestion_failed(db, document.id, str(exc))
            raise


def clean_pdf_text(raw_text: str, repeated_lines: set[str] | None = None) -> str:
    repeated_lines = repeated_lines or set()
    text = unicodedata.normalize("NFKC", raw_text or "").replace("\x00", " ")
    text = remove_broken_ocr_glyphs(text)
    text = re.sub(r"/H17040|H17040", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBM\.indd\b.*?(?=\s|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPlate\s+[A-Za-z0-9.-]+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\uf0b7\u2022\u25aa\u25cf]", " - ", text)
    text = re.sub(r"[^\S\r\n]+", " ", text)
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"(?<=\w)\s*-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(clean_pdf_line(line, repeated_lines=repeated_lines) for line in text.splitlines())
    text = "\n".join(line for line in text.splitlines() if line.strip())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_pdf_line(line: str, repeated_lines: set[str] | None = None) -> str:
    repeated_lines = repeated_lines or set()
    stripped = line.strip()
    lower = stripped.lower()
    if not stripped:
        return ""
    if normalize_repeated_line(stripped) in repeated_lines:
        return ""
    if is_standalone_page_number(stripped):
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
    return collapse_repeated_words(stripped)


def remove_broken_ocr_glyphs(text: str) -> str:
    replacements = {
        "\u00ad": "",
        "\ufffd": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F\u2010-\u204A]", " ", text)
    return text


def collapse_repeated_words(line: str) -> str:
    words = line.split()
    if len(words) < 6:
        return line
    collapsed: list[str] = []
    for word in words:
        if len(collapsed) >= 2 and collapsed[-1].lower() == word.lower() and collapsed[-2].lower() == word.lower():
            continue
        collapsed.append(word)
    return " ".join(collapsed)


def is_standalone_page_number(line: str) -> bool:
    return bool(re.fullmatch(r"(page\s*)?\d{1,4}", line.strip(), flags=re.IGNORECASE))


def normalize_repeated_line(line: str) -> str:
    normalized = re.sub(r"\d+", "#", line.lower())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .:-|")


def detect_repeated_page_lines(raw_pages: list[str]) -> set[str]:
    counts: dict[str, int] = {}
    page_total = len(raw_pages)
    if page_total < 4:
        return set()
    for raw_page in raw_pages:
        page_seen: set[str] = set()
        lines = [line.strip() for line in (raw_page or "").splitlines() if line.strip()]
        candidates = lines[:5] + lines[-5:]
        for line in candidates:
            normalized = normalize_repeated_line(line)
            if 4 <= len(normalized) <= 120 and not is_standalone_page_number(line):
                page_seen.add(normalized)
        for normalized in page_seen:
            counts[normalized] = counts.get(normalized, 0) + 1
    threshold = max(3, int(page_total * 0.35))
    return {line for line, count in counts.items() if count >= threshold}


def is_low_value_page(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return True
    lower = "\n".join(lines).lower()
    word_count = len(re.findall(r"[a-zA-Z][a-zA-Z'-]+", text))
    if word_count < 4:
        return True
    heading = lines[0].lower().strip(" .:-")
    toc_like_lines = sum(1 for line in lines if re.search(r"\.{3,}\s*\d+$|^\d+(\.\d+)*\s+.+\s+\d+$", line))
    if heading in {"contents", "table of contents"} and toc_like_lines >= 3:
        return True
    reference_hits = len(re.findall(r"\bet al\.|\bdoi\b|https?://|\bISBN\b|\bvol\.|\bpp\.", text, flags=re.IGNORECASE))
    if heading in {"references", "bibliography", "index"} and reference_hits >= 3:
        return True
    if reference_hits >= 8 and word_count < 220:
        return True
    quality = assess_chunk_quality(text)
    return quality.is_noisy and quality.quality_score < 0.45


def split_into_sections(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        compact = " ".join(text.split())
        return [{"text": compact, "section_title": infer_section_title(compact), "chapter_title": ""}] if compact else []

    sections: list[dict[str, str]] = []
    current_title = ""
    current_chapter = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        body = " ".join(" ".join(buffer).split()).strip()
        if body:
            sections.append({"text": body, "section_title": current_title, "chapter_title": current_chapter})
        buffer = []

    for line in lines:
        if is_probable_heading(line):
            flush()
            if re.search(r"\bchapter\b|\bunit\b", line, flags=re.IGNORECASE):
                current_chapter = line[:120]
            current_title = line[:120]
            continue
        buffer.append(line)
    flush()
    return sections or [{"text": " ".join(text.split()), "section_title": infer_section_title(text), "chapter_title": ""}]


def split_section_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    paragraphs = paragraph_blocks(text)
    if not paragraphs:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    target_size = max(400, chunk_size)
    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > target_size:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            chunks.extend(split_text(paragraph, target_size, chunk_overlap))
            continue
        if current and current_len + paragraph_len + 2 > target_size:
            chunks.append(" ".join(current).strip())
            overlap_text = trailing_overlap_text(chunks[-1], chunk_overlap)
            current = [overlap_text] if overlap_text else []
            current_len = len(overlap_text)
        current.append(paragraph)
        current_len += paragraph_len + 2
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if len(chunk.split()) >= 5]


def paragraph_blocks(text: str) -> list[str]:
    rough_blocks = re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-Z][a-z].{20,})", text)
    blocks = []
    for block in rough_blocks:
        cleaned = " ".join(block.split()).strip()
        if cleaned:
            blocks.append(cleaned)
    return blocks


def trailing_overlap_text(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    boundary = tail.find(". ")
    if boundary >= 0 and boundary + 2 < len(tail):
        return tail[boundary + 2 :].strip()
    return tail.strip()


def is_probable_heading(line: str) -> bool:
    stripped = line.strip(" :-")
    if not (4 <= len(stripped) <= 120):
        return False
    if stripped.endswith(".") or stripped.endswith(","):
        return False
    words = stripped.split()
    if len(words) > 14:
        return False
    if re.match(r"^(chapter|section|unit|part)\s+\d+", stripped, flags=re.IGNORECASE):
        return True
    title_case_words = sum(1 for word in words if word[:1].isupper())
    if title_case_words / max(len(words), 1) >= 0.65:
        return True
    return stripped.isupper() and len(words) >= 2


def dedupe_parsed_chunks(chunks: list[ParsedChunk]) -> list[ParsedChunk]:
    seen: set[str] = set()
    deduped: list[ParsedChunk] = []
    for chunk in chunks:
        content_hash = stable_content_hash(chunk.text)
        if content_hash in seen:
            continue
        seen.add(content_hash)
        deduped.append(
            ParsedChunk(
                text=chunk.text,
                page_number=chunk.page_number,
                chunk_index=len(deduped),
                section_title=chunk.section_title,
                chapter_title=chunk.chapter_title,
            )
        )
    return deduped


def filter_quality_chunks(chunks: list[ParsedChunk]) -> list[ParsedChunk]:
    retained: list[ParsedChunk] = []
    for chunk in chunks:
        quality = assess_chunk_quality(chunk.text)
        if quality.is_noisy or quality.quality_score < 0.6:
            continue
        retained.append(
            ParsedChunk(
                text=chunk.text,
                page_number=chunk.page_number,
                chunk_index=len(retained),
                section_title=chunk.section_title,
                chapter_title=chunk.chapter_title,
            )
        )
    return retained


def remove_existing_duplicate_chunks(db: Session, chunks: list[ParsedChunk], document_id: str) -> list[ParsedChunk]:
    if not chunks:
        return []
    hashes = [stable_content_hash(chunk.text) for chunk in chunks]
    existing_hashes = {
        row[0]
        for row in (
            db.query(DocumentChunk.content_hash)
            .filter(DocumentChunk.content_hash.in_(hashes))
            .filter(DocumentChunk.document_id != document_id)
            .all()
        )
        if row[0]
    }
    retained: list[ParsedChunk] = []
    for chunk, chunk_hash in zip(chunks, hashes):
        if chunk_hash in existing_hashes:
            continue
        retained.append(
            ParsedChunk(
                text=chunk.text,
                page_number=chunk.page_number,
                chunk_index=len(retained),
                section_title=chunk.section_title,
                chapter_title=chunk.chapter_title,
            )
        )
    return retained


def title_from_filename(filename: str) -> str:
    title = Path(filename).stem
    title = re.sub(r"[_-]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title.title() if title else filename


def extract_page_text_with_ocr(
    pdf_path: Path,
    page_number: int,
    log: Callable[[str, str], None] | None = None,
) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
        from PIL import ImageFilter, ImageOps
    except ImportError:
        if log:
            log("OCR packages are not installed. Install pdf2image, pytesseract, and Pillow to process scanned PDFs.", "warning")
        return ""

    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    convert_options = {
        "first_page": page_number,
        "last_page": page_number,
        "dpi": settings.ocr_dpi,
        "fmt": "png",
        "thread_count": 1,
    }
    if settings.poppler_path:
        convert_options["poppler_path"] = settings.poppler_path

    images = []
    try:
        images = convert_from_path(str(pdf_path), **convert_options)
        if not images:
            return ""
        image = ImageOps.grayscale(images[0])
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(
            image,
            lang=settings.ocr_language,
            config=settings.ocr_config,
        ) or ""
        if text.strip() and log:
            log(f"Page {page_number}: OCR extracted text successfully.", "info")
        return text
    except Exception as exc:
        if log:
            log(f"Page {page_number}: OCR failed ({exc}).", "warning")
        return ""
    finally:
        for image in images:
            try:
                image.close()
            except Exception:
                pass


def is_local_qdrant_storage_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "out of bounds" in message and "axis" in message:
        return True
    return any(
        pattern in message
        for pattern in [
            "cannot start a transaction within a transaction",
            "cannot start transaction within transaction",
            "operands could not be broadcast together",
            "storage folder",
            "already accessed by another instance",
        ]
    )


def is_qdrant_collection_missing_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "collection" in message and (
        "not found" in message
        or "doesn't exist" in message
        or "does not exist" in message
        or "status code: 404" in message
    )


def mark_ingestion_failed(db: Session, document_id: str, error_message: str) -> None:
    try:
        db.rollback()
    except Exception:
        pass
    document = db.get(Document, document_id)
    if not document:
        return
    document.status = DocumentStatus.failed
    document.error_message = error_message
    document.ingestion_step = "Failed"
    document.ingestion_completed_at = datetime.utcnow()
    db.add(DocumentIngestionLog(document_id=document_id, level="error", message=f"Ingestion failed: {error_message}"))
    commit_with_retry(db)


def commit_with_retry(db: Session, attempts: int = 8, delay_seconds: float = 0.25) -> None:
    for attempt in range(attempts):
        try:
            db.commit()
            return
        except OperationalError as exc:
            message = str(exc).lower()
            if "cannot commit - no transaction is active" in message:
                try:
                    db.rollback()
                except Exception:
                    pass
                return
            if "database is locked" not in message or attempt == attempts - 1:
                db.rollback()
                raise
            db.rollback()
            time.sleep(delay_seconds * (attempt + 1))


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


def stable_content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def infer_dental_specialty(text: str) -> str:
    lower = text.lower()
    mapping = [
        ("orthodont", "orthodontics"),
        ("endodont", "endodontics"),
        ("periodont", "periodontology"),
        ("prosthodont", "prosthodontics"),
        ("radiolog", "oral_and_maxillofacial_radiology"),
        ("maxillofacial", "oral_and_maxillofacial_surgery"),
        ("oral surgery", "oral_and_maxillofacial_surgery"),
        ("implant", "implant_dentistry"),
        ("tmj", "temporomandibular_disorders"),
        ("caries", "operative_dentistry"),
    ]
    for needle, specialty in mapping:
        if needle in lower:
            return specialty
    return "general_dentistry"


def infer_chunk_topic(text: str, fallback: str) -> str:
    lower = text.lower()
    mapping = [
        ("caries", "dental_caries"),
        ("implant", "implants_and_temporary_anchorage"),
        ("anchorage", "orthodontic_anchorage"),
        ("ceph", "cephalometrics"),
        ("cleft", "cleft_lip_and_palate"),
        ("tmj", "temporomandibular_disorders"),
        ("orthognathic", "orthognathic_surgery"),
        ("trauma", "dental_trauma"),
        ("bracket", "orthodontic_appliances"),
        ("aligner", "aligner_therapy"),
        ("occlusion", "occlusion"),
    ]
    for needle, topic in mapping:
        if needle in lower:
            return topic
    return fallback


def infer_difficulty_level(title: str) -> str:
    lower = title.lower()
    if re.search(r"\b(fcps|postgraduate|advanced|surgery|cephalometric|biomechanics)\b", lower):
        return "advanced"
    if re.search(r"\b(handbook|clinical|principles|contemporary)\b", lower):
        return "intermediate"
    return "general"


def infer_section_title(text: str) -> str:
    first = (text or "").strip().split(". ")[0].strip()
    if 8 <= len(first) <= 90 and not first.endswith("?"):
        return first[:90]
    return ""
