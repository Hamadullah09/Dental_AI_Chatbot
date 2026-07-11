from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from qdrant_client.http import models as qmodels
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentVisual
from app.services.embeddings import get_embedding_model
from app.services.vector_store import ensure_qdrant_collection, get_qdrant_client


CAPTION_RE = re.compile(
    r"\b(?P<label>fig(?:ure)?\.?|table|chart|diagram|flowchart)\s*"
    r"(?P<number>[0-9]+(?:[-.][0-9A-Za-z]+)?)?[:.\-\s]+(?P<caption>.{8,260})",
    re.IGNORECASE,
)


@dataclass
class ExtractedVisual:
    visual_id: str
    document_id: str
    document_name: str
    page_number: int
    visual_type: str
    image_path: str
    caption_text: str
    nearby_text: str
    generated_description: str
    related_chunk_ids: list[str]
    quality_score: float
    review_status: str = "reviewed"

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part.strip()
            for part in [self.caption_text, self.nearby_text, self.generated_description]
            if part and part.strip()
        )


def extract_and_index_document_visuals(
    db: Session,
    document: Document,
    *,
    embedding_model=None,
    qdrant=None,
    log: Callable[[str, str], None] | None = None,
) -> int:
    settings = get_settings()
    if not settings.enable_multimodal_rag:
        return 0
    pdf_path = Path(document.storage_path)
    if not pdf_path.is_absolute():
        pdf_path = Path.cwd() / pdf_path
    if not pdf_path.exists():
        if log:
            log(f"Visual extraction skipped; file not found: {pdf_path}", "warning")
        return 0

    output_dir = settings.extracted_visuals_dir / document.id
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_chunks = load_page_chunks(db, document.id)
    visuals: list[ExtractedVisual] = []
    visuals.extend(extract_with_pymupdf(pdf_path, document, output_dir, page_chunks, log))
    visuals.extend(extract_tables_with_pdfplumber(pdf_path, document, output_dir, page_chunks, log))
    visuals = dedupe_visuals(visuals)
    if not visuals:
        return 0

    db.query(DocumentVisual).filter(DocumentVisual.document_id == document.id).delete()
    db.flush()

    embedding_model = embedding_model or get_embedding_model()
    qdrant = qdrant or get_qdrant_client()
    vector_size = int(embedding_model.get_sentence_embedding_dimension() or 384)
    ensure_qdrant_collection(qdrant, settings.qdrant_collection, vector_size)
    vectors = embedding_model.encode([visual.searchable_text for visual in visuals])
    points: list[qmodels.PointStruct] = []
    for visual, vector in zip(visuals, vectors):
        point_id = str(uuid.uuid4())
        visual_record = DocumentVisual(
            visual_id=visual.visual_id,
            document_id=visual.document_id,
            document_name=visual.document_name,
            page_number=visual.page_number,
            visual_type=visual.visual_type,
            image_path=visual.image_path,
            caption_text=visual.caption_text,
            nearby_text=visual.nearby_text,
            generated_description=visual.generated_description,
            related_chunk_ids=json.dumps(visual.related_chunk_ids),
            quality_score=visual.quality_score,
            review_status=visual.review_status,
            content_hash=visual_content_hash(visual),
            qdrant_point_id=point_id,
        )
        db.add(visual_record)
        payload = visual_payload(visual, point_id)
        points.append(qmodels.PointStruct(id=point_id, vector=vector.tolist(), payload=payload))

    if points:
        qdrant.upsert(collection_name=settings.qdrant_collection, points=points)
    db.flush()
    return len(visuals)


def extract_with_pymupdf(
    pdf_path: Path,
    document: Document,
    output_dir: Path,
    page_chunks: dict[int, list[DocumentChunk]],
    log: Callable[[str, str], None] | None,
) -> list[ExtractedVisual]:
    try:
        import fitz
    except ImportError:
        if log:
            log("PyMuPDF is not installed; skipping page/image visual extraction.", "warning")
        return []

    settings = get_settings()
    visuals: list[ExtractedVisual] = []
    with fitz.open(str(pdf_path)) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            page_text = page.get_text("text") or ""
            captions = detect_captions(page_text)
            chunks = page_chunks.get(page_number, [])
            nearby_text = nearby_text_for_page(chunks, page_text)

            snapshot_path = output_dir / f"page_{page_number:04d}_snapshot.png"
            if captions:
                matrix = fitz.Matrix(settings.visual_page_snapshot_zoom, settings.visual_page_snapshot_zoom)
                page.get_pixmap(matrix=matrix, alpha=False).save(snapshot_path)
                visuals.append(
                    build_visual(
                        document=document,
                        page_number=page_number,
                        visual_type="page_snapshot",
                        image_path=snapshot_path,
                        caption_text=best_caption(captions, "page_snapshot"),
                        nearby_text=nearby_text,
                        related_chunk_ids=[chunk.qdrant_point_id for chunk in chunks[:4]],
                    )
                )

            for image_index, image in enumerate(page.get_images(full=True), start=1):
                xref = image[0]
                try:
                    pixmap = fitz.Pixmap(pdf, xref)
                    if pixmap.n >= 5:
                        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                    image_path = output_dir / f"page_{page_number:04d}_image_{image_index:02d}.png"
                    pixmap.save(image_path)
                except Exception as exc:
                    if log:
                        log(f"Page {page_number}: embedded image {image_index} extraction failed ({exc}).", "warning")
                    continue
                caption = nearest_caption(captions, image_index) or best_caption(captions, "figure")
                visuals.append(
                    build_visual(
                        document=document,
                        page_number=page_number,
                        visual_type=classify_visual_type(caption, fallback="figure"),
                        image_path=image_path,
                        caption_text=caption,
                        nearby_text=nearby_text,
                        related_chunk_ids=[chunk.qdrant_point_id for chunk in chunks[:4]],
                    )
                )

            for caption_index, caption in enumerate(captions[:4], start=1):
                if not caption:
                    continue
                caption_path = output_dir / f"page_{page_number:04d}_caption_region_{caption_index:02d}.png"
                crop_caption_region(page, caption_path, settings.visual_page_snapshot_zoom)
                visuals.append(
                    build_visual(
                        document=document,
                        page_number=page_number,
                        visual_type=classify_visual_type(caption, fallback="diagram"),
                        image_path=caption_path,
                        caption_text=caption,
                        nearby_text=nearby_text,
                        related_chunk_ids=[chunk.qdrant_point_id for chunk in chunks[:4]],
                    )
                )
    return visuals


def extract_tables_with_pdfplumber(
    pdf_path: Path,
    document: Document,
    output_dir: Path,
    page_chunks: dict[int, list[DocumentChunk]],
    log: Callable[[str, str], None] | None,
) -> list[ExtractedVisual]:
    try:
        import pdfplumber
    except ImportError:
        if log:
            log("pdfplumber is not installed; skipping table extraction.", "warning")
        return []

    visuals: list[ExtractedVisual] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                chunks = page_chunks.get(page_number, [])
                page_text = page.extract_text() or ""
                if "table" not in page_text.lower():
                    continue
                nearby_text = nearby_text_for_page(chunks, page_text)
                tables = page.find_tables() or []
                for table_index, table in enumerate(tables[:5], start=1):
                    image_path = output_dir / f"page_{page_number:04d}_table_{table_index:02d}.png"
                    try:
                        page.crop(table.bbox).to_image(resolution=150).save(str(image_path), format="PNG")
                    except Exception:
                        # Some Windows installs lack ImageMagick support in pdfplumber; keep page snapshot fallback.
                        image_path = output_dir / f"page_{page_number:04d}_snapshot.png"
                    caption = find_table_caption(page_text, table_index)
                    visuals.append(
                        build_visual(
                            document=document,
                            page_number=page_number,
                            visual_type="table",
                            image_path=image_path,
                            caption_text=caption,
                            nearby_text=nearby_text,
                            related_chunk_ids=[chunk.qdrant_point_id for chunk in chunks[:4]],
                        )
                    )
    except Exception as exc:
        if log:
            log(f"pdfplumber table extraction failed ({exc}).", "warning")
    return visuals


def load_page_chunks(db: Session, document_id: str) -> dict[int, list[DocumentChunk]]:
    rows = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        .all()
    )
    pages: dict[int, list[DocumentChunk]] = {}
    for chunk in rows:
        if chunk.page_number is None:
            continue
        pages.setdefault(chunk.page_number, []).append(chunk)
    return pages


def detect_captions(text: str) -> list[str]:
    captions: list[str] = []
    for line in text.splitlines():
        cleaned = " ".join(line.split())
        match = CAPTION_RE.search(cleaned)
        if match:
            captions.append(cleaned[:320])
    return captions


def build_visual(
    *,
    document: Document,
    page_number: int,
    visual_type: str,
    image_path: Path,
    caption_text: str,
    nearby_text: str,
    related_chunk_ids: list[str],
) -> ExtractedVisual:
    generated_description = generate_visual_description(visual_type, caption_text, nearby_text, document)
    return ExtractedVisual(
        visual_id=str(uuid.uuid4()),
        document_id=document.id,
        document_name=document.canonical_title or document.title or document.original_filename,
        page_number=page_number,
        visual_type=visual_type,
        image_path=str(image_path).replace("\\", "/"),
        caption_text=caption_text,
        nearby_text=nearby_text[:1200],
        generated_description=generated_description,
        related_chunk_ids=[chunk_id for chunk_id in related_chunk_ids if chunk_id],
        quality_score=visual_quality_score(visual_type, caption_text, nearby_text),
    )


def generate_visual_description(visual_type: str, caption: str, nearby_text: str, document: Document) -> str:
    title = document.canonical_title or document.title or document.original_filename
    parts = [f"{visual_type.replace('_', ' ')} from {title}"]
    if caption:
        parts.append(f"Caption: {caption}")
    if nearby_text:
        parts.append(f"Nearby page context: {nearby_text[:360]}")
    return ". ".join(parts)


def visual_quality_score(visual_type: str, caption: str, nearby_text: str) -> float:
    score = 0.45
    if caption:
        score += 0.3
    if visual_type != "page_snapshot":
        score += 0.15
    if len(nearby_text.split()) >= 35:
        score += 0.1
    return round(min(score, 1.0), 3)


def nearby_text_for_page(chunks: list[DocumentChunk], page_text: str) -> str:
    chunk_text = " ".join(chunk.text[:500] for chunk in chunks[:4] if chunk.text)
    text = chunk_text or page_text[:1200]
    return " ".join(text.split())[:1400]


def best_caption(captions: list[str], visual_type: str) -> str:
    if not captions:
        return ""
    if visual_type == "page_snapshot":
        return captions[0]
    return next((caption for caption in captions if visual_type in caption.lower()), captions[0])


def nearest_caption(captions: list[str], image_index: int) -> str:
    if not captions:
        return ""
    return captions[min(image_index - 1, len(captions) - 1)]


def classify_visual_type(caption: str, fallback: str = "unknown") -> str:
    lower = caption.lower()
    if "flowchart" in lower:
        return "flowchart"
    if "diagram" in lower:
        return "diagram"
    if "chart" in lower or "graph" in lower:
        return "chart"
    if "table" in lower:
        return "table"
    if "fig" in lower or "figure" in lower:
        return "figure"
    return fallback


def crop_caption_region(page, output_path: Path, zoom: float) -> None:
    rect = page.rect
    height = rect.height
    clip = (rect.x0, max(rect.y0, height * 0.45), rect.x1, rect.y1)
    import fitz

    page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(*clip), alpha=False).save(output_path)


def find_table_caption(text: str, table_index: int) -> str:
    captions = [caption for caption in detect_captions(text) if "table" in caption.lower()]
    if captions:
        return captions[min(table_index - 1, len(captions) - 1)]
    return f"Table {table_index}"


def dedupe_visuals(visuals: list[ExtractedVisual]) -> list[ExtractedVisual]:
    seen: set[str] = set()
    deduped: list[ExtractedVisual] = []
    for visual in visuals:
        key = visual_content_hash(visual)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(visual)
    return deduped


def visual_content_hash(visual: ExtractedVisual) -> str:
    payload = f"{visual.document_id}|{visual.page_number}|{visual.visual_type}|{visual.caption_text}|{visual.image_path}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def visual_payload(visual: ExtractedVisual, point_id: str) -> dict:
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
        "related_chunk_ids": visual.related_chunk_ids,
        "quality_score": visual.quality_score,
        "review_status": visual.review_status,
        "content_hash": visual_content_hash(visual),
        "text": visual.searchable_text,
    }


def image_url_for_path(image_path: str) -> str:
    normalized = image_path.replace("\\", "/")
    marker = "uploads/"
    index = normalized.find(marker)
    if index >= 0:
        return "/" + normalized[index:]
    return "/" + normalized.lstrip("/")
