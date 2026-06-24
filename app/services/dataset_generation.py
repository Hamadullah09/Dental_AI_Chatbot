import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Document, DocumentChunk
from app.services.chunk_quality import assess_chunk_quality


CATEGORIES = [
    "patient_friendly",
    "student_explanation",
    "short_answer",
    "roman_urdu",
    "safety_refusal",
    "emergency_referral",
    "insufficient_evidence",
]

OUTPUT_PATH = Path("draft_dental_qa.jsonl")
SKIPPED_PATH = Path("skipped_chunks.jsonl")
STATUS_PATH = Path("dataset_generation_status.json")
REVIEW_CSV_PATH = Path("Database Q&A.csv")

REVIEW_CSV_FIELDS = [
    "instruction",
    "input",
    "output",
    "category",
    "source_document",
    "source_page",
    "source_chunk_id",
    "correctness",
    "safety",
    "language_quality",
    "approved_or_rejected",
    "reviewer_notes",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(status: dict[str, Any]) -> None:
    payload = {"updated_at": _utc_now(), **status}
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_dataset_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {
            "state": "idle",
            "processed_chunks": 0,
            "generated_items": 0,
            "skipped_chunks": 0,
            "output_path": str(OUTPUT_PATH),
            "skipped_path": str(SKIPPED_PATH),
            "review_csv_path": str(REVIEW_CSV_PATH),
            "duplicate_chunks": 0,
            "document_id": None,
            "document_name": None,
        }
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _processed_chunk_ids(output_path: Path) -> set[str]:
    processed: set[str] = set()
    for row in _read_jsonl(output_path) or []:
        chunk_id = row.get("source_chunk_id")
        if chunk_id:
            processed.add(str(chunk_id))
    return processed


def _processed_chunk_indices_for_document(output_path: Path, document_name: str | None) -> set[int]:
    if not document_name:
        return set()
    processed: set[int] = set()
    for row in _read_jsonl(output_path) or []:
        if str(row.get("source_document") or "") != document_name:
            continue
        value = row.get("source_chunk_index")
        try:
            if value is not None:
                processed.add(int(value))
        except (TypeError, ValueError):
            continue
    return processed


def _build_prompt(chunk: dict[str, Any], examples_per_chunk: int) -> str:
    categories = ", ".join(CATEGORIES)
    return f"""
Create {examples_per_chunk} draft dental Q&A examples from the provided evidence chunk.

Rules:
- Use only the evidence in the chunk.
- Do not invent facts.
- Do not diagnose or prescribe.
- If the chunk has insufficient evidence, create an insufficient_evidence example.
- Include patient-safe wording and citations in the answer text when helpful.
- Return strict JSON only with key "items" containing an array.
- Each item must include: instruction, input, output, category.
- category must be one of: {categories}

Source document: {chunk.get("document_name")}
Source page: {chunk.get("page_number")}
Chunk text:
{chunk.get("text", "")[:3500]}
""".strip()


def _parse_items(content: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        payload = json.loads(content[start:end + 1])
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def _generate_items_openai(
    client: OpenAI,
    models: list[str],
    chunk: dict[str, Any],
    examples_per_chunk: int,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "You generate expert-review draft dental Q&A from evidence chunks. Return valid JSON only.",
                    },
                    {"role": "user", "content": _build_prompt(chunk, examples_per_chunk)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            return _parse_items(content)
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            if "invalid model" in message or "model_not_found" in message or "does not exist" in message:
                continue
            raise
    raise RuntimeError(f"No configured OpenAI model worked. Last error: {last_error}")


def _openai_model_candidates(primary: str, fallback_csv: str) -> list[str]:
    seen: set[str] = set()
    models: list[str] = []
    for model in [primary, *fallback_csv.split(",")]:
        model = model.strip()
        if model and model not in seen:
            seen.add(model)
            models.append(model)
    return models


def _generate_items_ollama(base_url: str, model: str, chunk: dict[str, Any], examples_per_chunk: int) -> list[dict[str, Any]]:
    prompt = (
        "You generate expert-review draft dental Q&A from evidence chunks. "
        "Return valid JSON only.\n\n"
        f"{_build_prompt(chunk, examples_per_chunk)}"
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Ollama is not reachable at {base_url}. Start Ollama and pull model '{model}'. {exc}") from exc
    content = raw.get("response") or "{}"
    return _parse_items(content)


def _chunk_payload(chunk: DocumentChunk, document: Document) -> dict[str, Any]:
    return {
        "chunk_id": chunk.qdrant_point_id,
        "document_id": document.id,
        "document_name": document.title or document.original_filename,
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "quality_score": chunk.quality_score,
        "is_noisy": chunk.is_noisy,
        "review_status": document.review_status.value,
        "document_type": document.document_type.value,
        "trust_level": document.trust_level.value,
    }


def _document_name(db: Session, document_id: str | None) -> str | None:
    if not document_id:
        return None
    document = db.get(Document, document_id)
    if not document:
        return None
    return document.title or document.original_filename


def _iter_clean_chunks(db: Session, min_quality: float, include_noisy: bool, document_id: str | None):
    query = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(Document.created_at.desc(), DocumentChunk.chunk_index.asc())
    )
    if document_id:
        query = query.filter(Document.id == document_id)
    for chunk, document in query.yield_per(100):
        quality = assess_chunk_quality(chunk.text)
        quality_score = float(chunk.quality_score or quality.quality_score or 0.0)
        is_noisy = bool(chunk.is_noisy or quality.is_noisy)
        if not include_noisy and (is_noisy or quality_score < min_quality):
            continue
        yield _chunk_payload(chunk, document)


def generate_dataset_from_db(
    *,
    limit: int | None = 25,
    examples_per_chunk: int = 5,
    min_quality: float = 0.6,
    include_noisy: bool = False,
    document_id: str | None = None,
    sleep_seconds: float = 0.0,
) -> dict[str, Any]:
    settings = get_settings()
    provider = settings.dataset_llm_provider.lower().strip()
    client = None
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when DATASET_LLM_PROVIDER=openai.")
        client = OpenAI(api_key=settings.openai_api_key)
        openai_models = _openai_model_candidates(settings.openai_model, settings.openai_model_fallbacks)
    elif provider != "ollama":
        raise RuntimeError("DATASET_LLM_PROVIDER must be 'ollama' or 'openai'.")
    else:
        openai_models = []

    already_processed = _processed_chunk_ids(OUTPUT_PATH)
    processed_chunks = 0
    generated_items = 0
    skipped_chunks = 0
    duplicate_chunks = 0

    with SessionLocal() as db:
        document_name = _document_name(db, document_id)
        processed_chunk_indices = _processed_chunk_indices_for_document(OUTPUT_PATH, document_name)

    _write_status({
        "state": "running",
        "processed_chunks": 0,
        "generated_items": 0,
        "skipped_chunks": 0,
        "duplicate_chunks": 0,
        "removed_existing_rows": 0,
        "document_id": document_id,
        "document_name": document_name,
        "output_path": str(OUTPUT_PATH),
        "skipped_path": str(SKIPPED_PATH),
        "review_csv_path": str(REVIEW_CSV_PATH),
        "provider": provider,
        "message": (
            f"Dataset generation started with {provider} for {document_name}."
            if document_name
            else f"Dataset generation started with {provider} for all PDFs."
        ),
    })

    with SessionLocal() as db, OUTPUT_PATH.open("a", encoding="utf-8") as output, SKIPPED_PATH.open("a", encoding="utf-8") as skipped:
        for chunk in _iter_clean_chunks(db, min_quality=min_quality, include_noisy=include_noisy, document_id=document_id):
            chunk_id = str(chunk.get("chunk_id") or "")
            chunk_index = chunk.get("chunk_index")
            if not chunk_id or chunk_id in already_processed or (
                document_name and chunk_index is not None and int(chunk_index) in processed_chunk_indices
            ):
                duplicate_chunks += 1
                continue
            try:
                if provider == "ollama":
                    items = _generate_items_ollama(settings.ollama_base_url, settings.ollama_model, chunk, examples_per_chunk)
                else:
                    items = _generate_items_openai(client, openai_models, chunk, examples_per_chunk)
                valid_count = 0
                for item in items:
                    category = item.get("category")
                    if category not in CATEGORIES:
                        category = "student_explanation"
                    row = {
                        "instruction": str(item.get("instruction") or "").strip(),
                        "input": str(item.get("input") or "").strip(),
                        "output": str(item.get("output") or "").strip(),
                        "category": category,
                        "source_document": chunk.get("document_name"),
                        "source_page": chunk.get("page_number"),
                        "source_chunk_id": chunk_id,
                        "source_chunk_index": chunk.get("chunk_index"),
                        "review_status": "pending_review",
                    }
                    if row["instruction"] and row["output"]:
                        output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        valid_count += 1
                output.flush()
                processed_chunks += 1
                generated_items += valid_count
                already_processed.add(chunk_id)
                if document_name and chunk_index is not None:
                    processed_chunk_indices.add(int(chunk_index))
                if valid_count == 0:
                    skipped.write(json.dumps({"chunk_id": chunk_id, "reason": "no_valid_items"}, ensure_ascii=False) + "\n")
                    skipped_chunks += 1
            except Exception as exc:
                skipped.write(json.dumps({"chunk_id": chunk_id, "reason": str(exc)}, ensure_ascii=False) + "\n")
                skipped.flush()
                skipped_chunks += 1
            _write_status({
                "state": "running",
                "processed_chunks": processed_chunks,
                "generated_items": generated_items,
                "skipped_chunks": skipped_chunks,
                "duplicate_chunks": duplicate_chunks,
                "removed_existing_rows": 0,
                "document_id": document_id,
                "document_name": document_name,
                "output_path": str(OUTPUT_PATH),
                "skipped_path": str(SKIPPED_PATH),
                "review_csv_path": str(REVIEW_CSV_PATH),
                "provider": provider,
                "message": f"Processed {processed_chunks} chunks. Skipped {duplicate_chunks} chunks already in the dataset.",
            })
            if sleep_seconds:
                time.sleep(sleep_seconds)
            if limit and processed_chunks >= limit:
                break

    result = {
        "state": "completed",
        "processed_chunks": processed_chunks,
        "generated_items": generated_items,
        "skipped_chunks": skipped_chunks,
        "duplicate_chunks": duplicate_chunks,
        "removed_existing_rows": 0,
        "document_id": document_id,
        "document_name": document_name,
        "output_path": str(OUTPUT_PATH),
        "skipped_path": str(SKIPPED_PATH),
        "review_csv_path": str(REVIEW_CSV_PATH),
        "provider": provider,
        "message": (
            f"Generated {generated_items} Q&A rows from {processed_chunks} chunks. "
            f"Skipped {duplicate_chunks} chunks already in the dataset."
        ),
    }
    export_review_csv()
    _write_status(result)
    return result


def generate_dataset_background(**kwargs: Any) -> None:
    try:
        generate_dataset_from_db(**kwargs)
    except Exception as exc:
        current = read_dataset_status()
        _write_status({
            **current,
            "state": "failed",
            "message": str(exc),
            "output_path": str(OUTPUT_PATH),
            "skipped_path": str(SKIPPED_PATH),
            "review_csv_path": str(REVIEW_CSV_PATH),
        })


def export_review_csv() -> Path:
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"{OUTPUT_PATH} does not exist yet.")
    with OUTPUT_PATH.open("r", encoding="utf-8") as source, REVIEW_CSV_PATH.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=REVIEW_CSV_FIELDS)
        writer.writeheader()
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            writer.writerow({field: row.get(field, "") for field in REVIEW_CSV_FIELDS})
    return REVIEW_CSV_PATH
