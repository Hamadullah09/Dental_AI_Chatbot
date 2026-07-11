from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "dental_ai.db"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "cleanup_reports"

USELESS_TITLE_PATTERNS = [
    r"\bspss\b",
    r"\bconference\b",
    r"\bbrochure\b",
    r"\bregistration\s+form\b",
    r"\btable\s+of\s+contents\b",
    r"\btoc\b",
    r"\beditorial\s+board\b",
    r"\bfuture\s+issues?\b",
    r"\badvertisement\b",
    r"\bcall\s+for\s+papers\b",
]

DENTAL_TERMS = [
    "dental",
    "dentistry",
    "tooth",
    "teeth",
    "oral",
    "orthodont",
    "endodont",
    "periodont",
    "prosthodont",
    "maxillofacial",
    "occlusion",
    "caries",
    "enamel",
    "dentin",
    "gingiva",
    "implant",
    "mandible",
    "maxilla",
    "cephalometric",
    "malocclusion",
    "tmj",
    "radiology",
]

REFERENCE_OR_ADMIN_PATTERNS = [
    r"^\s*references?\s*$",
    r"^\s*bibliography\s*$",
    r"^\s*index\s*$",
    r"^\s*table\s+of\s+contents\s*$",
    r"\bregistration\s+form\b",
    r"\bconference\s+brochure\b",
    r"\beditorial\s+board\b",
    r"\bfuture\s+issues?\b",
    r"\bput\s+a\s+tick\b",
    r"\bquestionnaire\b",
    r"\bsurvey\s+form\b",
]


@dataclass
class DocumentRecord:
    id: str
    filename: str
    original_filename: str
    storage_path: str
    status: str
    title: str
    author_or_source: str
    edition: str
    publication_year: int | None
    document_type: str
    trust_level: str
    review_status: str
    specialty: str
    language: str
    file_hash: str
    chunk_count: int
    ocr_used: bool
    created_at: str
    updated_at: str
    chunks: list["ChunkRecord"] = field(default_factory=list)


@dataclass
class ChunkRecord:
    id: str
    document_id: str
    qdrant_point_id: str
    chunk_index: int
    page_number: int | None
    text: str
    token_estimate: int
    quality_score: float
    is_noisy: bool
    noise_reasons: list[str]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to dental_ai.db")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Directory for CSV/JSON reports")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Audit only; do not mutate data")
    parser.add_argument(
        "--sample-similarity",
        action="store_true",
        help="Enable slower sampled content similarity for near-duplicate documents.",
    )


def report_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_documents(db_path: str | Path) -> list[DocumentRecord]:
    with connect(db_path) as conn:
        docs = [
            DocumentRecord(
                id=row["id"],
                filename=row["filename"] or "",
                original_filename=row["original_filename"] or "",
                storage_path=row["storage_path"] or "",
                status=row["status"] or "",
                title=row["title"] or "",
                author_or_source=row["author_or_source"] or "",
                edition=row["edition"] or "",
                publication_year=row["publication_year"],
                document_type=row["document_type"] or "",
                trust_level=row["trust_level"] or "",
                review_status=row["review_status"] or "",
                specialty=row["specialty"] or "",
                language=row["language"] or "",
                file_hash=row["file_hash"] or "",
                chunk_count=row["chunk_count"] or 0,
                ocr_used=bool(row["ocr_used"]),
                created_at=row["created_at"] or "",
                updated_at=row["updated_at"] or "",
            )
            for row in conn.execute("SELECT * FROM documents ORDER BY created_at, original_filename")
        ]
        by_id = {doc.id: doc for doc in docs}
        for row in conn.execute("SELECT * FROM document_chunks ORDER BY document_id, chunk_index"):
            reasons = parse_noise_reasons(row["noise_reasons"])
            chunk = ChunkRecord(
                id=row["id"],
                document_id=row["document_id"],
                qdrant_point_id=row["qdrant_point_id"] or "",
                chunk_index=row["chunk_index"] or 0,
                page_number=row["page_number"],
                text=row["text"] or "",
                token_estimate=row["token_estimate"] or 0,
                quality_score=float(row["quality_score"] or 0.0),
                is_noisy=bool(row["is_noisy"]),
                noise_reasons=reasons,
            )
            if chunk.document_id in by_id:
                by_id[chunk.document_id].chunks.append(chunk)
        return docs


def parse_noise_reasons(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
        if isinstance(data, list):
            return [str(item) for item in data]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in value.split(",") if part.strip()]


def normalize_title(value: str) -> str:
    text = value or ""
    text = Path(text).stem
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(pdf|final|copy|highlighted|scan|scanned|ebook|book)\b", " ", text)
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\s+edition\b", r"\1 edition", text)
    text = re.sub(r"[_\-.,()[\]{}]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def canonical_title(doc: DocumentRecord) -> str:
    return normalize_spaces(doc.title or Path(doc.original_filename or doc.filename).stem)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text_for_hash(text).encode("utf-8")).hexdigest()


def normalize_text_for_hash(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"(?<=\w)-\s+(?=\w)", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def text_fingerprint(chunks: list[ChunkRecord], sample_size: int = 6) -> str:
    if not chunks:
        return ""
    sample: list[ChunkRecord] = []
    sample.extend(chunks[: max(1, sample_size // 3)])
    middle = len(chunks) // 2
    sample.extend(chunks[max(0, middle - 1): middle + 1])
    sample.extend(chunks[-max(1, sample_size // 3):])
    text = " ".join(chunk.text[:700] for chunk in sample)
    return content_hash(text[:5000])


def sampled_text(chunks: list[ChunkRecord], limit: int = 4000) -> str:
    if not chunks:
        return ""
    parts = []
    for chunk in chunks[:2] + chunks[len(chunks) // 2: len(chunks) // 2 + 1] + chunks[-2:]:
        parts.append(chunk.text[:900])
    return normalize_text_for_hash(" ".join(parts))[:limit]


def sampled_similarity(left: DocumentRecord, right: DocumentRecord) -> float:
    return SequenceMatcher(None, sampled_text(left.chunks), sampled_text(right.chunks)).ratio()


def infer_language(doc: DocumentRecord) -> tuple[str, list[str]]:
    combined = " ".join([doc.title, doc.original_filename, " ".join(chunk.text[:250] for chunk in doc.chunks[:5])])
    lower = combined.lower()
    reasons: list[str] = []
    if "chinese" in lower:
        return "Chinese", ["title_or_text_mentions_chinese"]
    if re.search(r"[\u4e00-\u9fff]", combined):
        return "Chinese", ["cjk_characters_detected"]
    if re.search(r"[\u0600-\u06ff]", combined):
        return "Urdu/Arabic", ["arabic_script_detected"]
    if doc.language and doc.language.lower() not in {"english", "en"}:
        reasons.append("stored_language_non_english")
        return doc.language, reasons
    return "English", reasons


def infer_document_type(doc: DocumentRecord) -> str:
    title = f"{doc.title} {doc.original_filename}".lower()
    if re.search(r"\bguideline|clinical practice guideline|consensus\b", title):
        return "guideline"
    if re.search(r"\bjournal|article|case report|study|trial|systematic review\b", title):
        return "research_article"
    if re.search(r"\bpatient|leaflet|brochure\b", title):
        return "patient_education"
    if re.search(r"\btextbook|handbook|manual|principles|contemporary|orthodontics|radiology\b", title):
        return "textbook"
    return doc.document_type or "other"


def infer_specialty(doc: DocumentRecord) -> str:
    text = f"{doc.title} {doc.original_filename} {doc.specialty}".lower()
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
        ("pediatric", "pediatric_dentistry"),
        ("paediatric", "pediatric_dentistry"),
        ("caries", "operative_dentistry"),
    ]
    for needle, specialty in mapping:
        if needle in text:
            return specialty
    return doc.specialty or "general_dentistry"


def infer_difficulty(doc: DocumentRecord) -> str:
    text = f"{doc.title} {doc.original_filename}".lower()
    if re.search(r"\bfcps|postgraduate|advanced|surgery|cephalometric|biomechanics\b", text):
        return "advanced"
    if re.search(r"\bhandbook|clinical|principles|contemporary\b", text):
        return "intermediate"
    return "general"


def infer_trust(doc: DocumentRecord, classification: str) -> str:
    if classification in {"QUARANTINE", "REMOVE_CANDIDATE"}:
        return "low"
    doc_type = infer_document_type(doc)
    if doc_type in {"guideline", "textbook"} and has_clinical_signal(doc):
        return "high"
    if doc_type == "research_article":
        return "medium"
    return "medium" if has_clinical_signal(doc) else "low"


def has_clinical_signal(doc: DocumentRecord) -> bool:
    combined = f"{doc.title} {doc.original_filename} " + " ".join(chunk.text[:500] for chunk in doc.chunks[:8])
    lower = combined.lower()
    return any(term in lower for term in DENTAL_TERMS)


def classify_document(doc: DocumentRecord, duplicate_ids: set[str]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    title = f"{doc.title} {doc.original_filename}".lower()
    chunk_count = len(doc.chunks)
    if doc.id in duplicate_ids:
        return "DUPLICATE", ["duplicate_of_better_copy"]
    if doc.status == "failed" or chunk_count == 0:
        return "REMOVE_CANDIDATE", ["failed_or_empty_document"]
    for pattern in USELESS_TITLE_PATTERNS:
        if re.search(pattern, title):
            reasons.append(f"title_matches:{pattern}")
    if reasons:
        return "QUARANTINE", reasons
    if not has_clinical_signal(doc):
        return "REVIEW", ["weak_dental_signal"]
    noisy_ratio = noisy_chunk_ratio(doc)
    if noisy_ratio > 0.5:
        return "REVIEW", [f"high_noisy_chunk_ratio:{noisy_ratio:.2f}"]
    metadata_issues = document_metadata_issues(doc)
    if metadata_issues:
        return "REVIEW", metadata_issues[:3]
    return "KEEP", ["useful_dental_content"]


def noisy_chunk_ratio(doc: DocumentRecord) -> float:
    if not doc.chunks:
        return 1.0
    noisy = sum(1 for chunk in doc.chunks if chunk.is_noisy or assess_text_quality(chunk.text)[0])
    return noisy / len(doc.chunks)


def document_metadata_issues(doc: DocumentRecord) -> list[str]:
    issues: list[str] = []
    inferred_language, language_reasons = infer_language(doc)
    if doc.language and inferred_language.lower() != doc.language.lower() and language_reasons:
        issues.append(f"language_mismatch:stored={doc.language}:inferred={inferred_language}")
    if doc.trust_level == "high" and not has_clinical_signal(doc):
        issues.append("high_trust_without_clear_dental_signal")
    if doc.review_status == "approved" and doc.trust_level == "high" and noisy_chunk_ratio(doc) > 0.35:
        issues.append("approved_high_trust_with_many_noisy_chunks")
    if not doc.title:
        issues.append("missing_title")
    if not doc.publication_year:
        issues.append("missing_publication_year")
    return issues


def duplicate_document_groups(
    docs: list[DocumentRecord],
    *,
    sample_similarity: bool = False,
) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    duplicate_ids: set[str] = set()
    exact_groups: dict[str, list[DocumentRecord]] = defaultdict(list)
    for doc in docs:
        key = doc.file_hash
        if key:
            exact_groups[key].append(doc)

    group_index = 1
    for key, group_docs in exact_groups.items():
        if len(group_docs) < 2:
            continue
        best = choose_best_document(group_docs)
        group_id = f"exact-{group_index:04d}"
        group_index += 1
        for doc in group_docs:
            duplicate = doc.id != best.id
            if duplicate:
                duplicate_ids.add(doc.id)
            rows.append(duplicate_row(group_id, "exact_file_hash", doc, best, 1.0, key, duplicate))

    candidate_pairs: set[tuple[str, str]] = set()
    docs_by_id = {doc.id: doc for doc in docs}
    buckets: dict[str, list[DocumentRecord]] = defaultdict(list)
    for doc in docs:
        normalized = normalize_title(doc.title or doc.original_filename)
        if not normalized:
            continue
        words = normalized.split()
        bucket_keys = {
            normalized,
            " ".join(words[:4]),
            re.sub(r"\b(edition|ed|vol|volume)\b.*$", "", normalized).strip(),
        }
        page_bucket = max(1, len(doc.chunks) // 25)
        bucket_keys.add(f"{words[0] if words else normalized}:{page_bucket}")
        for key in bucket_keys:
            if key:
                buckets[key].append(doc)

    for bucket_docs in buckets.values():
        if len(bucket_docs) < 2 or len(bucket_docs) > 24:
            continue
        for index, left in enumerate(bucket_docs):
            for right in bucket_docs[index + 1:]:
                candidate_pairs.add(tuple(sorted([left.id, right.id])))

    for left_id, right_id in candidate_pairs:
            left = docs_by_id[left_id]
            right = docs_by_id[right_id]
            title_score = SequenceMatcher(None, normalize_title(left.title or left.original_filename), normalize_title(right.title or right.original_filename)).ratio()
            chunk_delta = abs(len(left.chunks) - len(right.chunks))
            max_chunks = max(len(left.chunks), len(right.chunks), 1)
            chunk_similarity = 1.0 - (chunk_delta / max_chunks)
            fingerprint_match = text_fingerprint(left.chunks) and text_fingerprint(left.chunks) == text_fingerprint(right.chunks)
            sample_score = sampled_similarity(left, right) if sample_similarity and (title_score > 0.72 or fingerprint_match) else 0.0
            near_score = max((title_score * 0.55) + (chunk_similarity * 0.2) + (sample_score * 0.25), 1.0 if fingerprint_match else 0.0)
            if near_score >= 0.86:
                best = choose_best_document([left, right])
                group_id = f"near-{group_index:04d}"
                group_index += 1
                for doc in [left, right]:
                    duplicate = doc.id != best.id
                    if duplicate:
                        duplicate_ids.add(doc.id)
                    rows.append(duplicate_row(group_id, "near_duplicate", doc, best, near_score, "", duplicate))
    return rows, duplicate_ids


def duplicate_row(group_id: str, match_type: str, doc: DocumentRecord, best: DocumentRecord, score: float, hash_value: str, duplicate: bool) -> dict[str, Any]:
    return {
        "duplicate_group_id": group_id,
        "match_type": match_type,
        "document_id": doc.id,
        "original_filename": doc.original_filename,
        "canonical_title": canonical_title(doc),
        "file_hash": doc.file_hash or hash_value,
        "chunk_count": len(doc.chunks),
        "quality_average": average_quality(doc),
        "recommended_action": "DUPLICATE" if duplicate else "KEEP_CANONICAL",
        "keep_document_id": best.id,
        "keep_filename": best.original_filename,
        "similarity_score": round(score, 4),
    }


def choose_best_document(docs: list[DocumentRecord]) -> DocumentRecord:
    return sorted(
        docs,
        key=lambda doc: (
            average_quality(doc),
            len(doc.chunks),
            1 if doc.publication_year else 0,
            doc.publication_year or 0,
            -len(doc.original_filename),
        ),
        reverse=True,
    )[0]


def average_quality(doc: DocumentRecord) -> float:
    if not doc.chunks:
        return 0.0
    return round(sum(chunk.quality_score for chunk in doc.chunks) / len(doc.chunks), 4)


def file_sha256(path_value: str) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_chunk_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    lines = [line.strip() for line in text.splitlines()]
    counts = Counter(line.lower() for line in lines if 4 <= len(line) <= 90)
    cleaned_lines = []
    for line in lines:
        lower = line.lower()
        if not line:
            continue
        if counts[lower] > 2:
            continue
        if re.fullmatch(r"\d{1,4}", line):
            continue
        if re.fullmatch(r"[\W\d_]{4,}", line):
            continue
        cleaned_lines.append(line)
    cleaned = " ".join(cleaned_lines) if cleaned_lines else text
    cleaned = re.sub(r"\bBM\.indd\b.*?(?=\s|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"/H17040|H17040", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def assess_text_quality(text: str) -> tuple[bool, list[str], float]:
    cleaned = clean_chunk_text(text)
    lower = cleaned.lower()
    reasons: list[str] = []
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", cleaned)
    word_count = len(words)
    score = 1.0
    if word_count < 35:
        reasons.append("very_short_text")
        score -= 0.35
    for pattern in REFERENCE_OR_ADMIN_PATTERNS:
        if re.search(pattern, lower):
            reasons.append("reference_admin_form_or_index")
            score -= 0.35
            break
    compact = re.sub(r"\s+", "", cleaned)
    if compact:
        non_alpha = sum(1 for char in compact if not char.isalpha())
        if non_alpha / len(compact) > 0.42:
            reasons.append("mostly_symbols_numbers_or_table_artifacts")
            score -= 0.35
    if words:
        very_short = sum(1 for word in words if len(word) <= 2)
        if very_short / len(words) > 0.35 and word_count > 40:
            reasons.append("ocr_or_layout_garbage")
            score -= 0.3
    score = max(0.0, min(1.0, round(score, 3)))
    return score < 0.6, reasons, score


def duplicate_chunk_rows(docs: list[DocumentRecord]) -> tuple[list[dict[str, Any]], set[str]]:
    groups: dict[str, list[tuple[DocumentRecord, ChunkRecord, str]]] = defaultdict(list)
    for doc in docs:
        for chunk in doc.chunks:
            cleaned = clean_chunk_text(chunk.text)
            if len(cleaned.split()) < 20:
                continue
            groups[content_hash(cleaned)].append((doc, chunk, cleaned))

    rows: list[dict[str, Any]] = []
    duplicate_point_ids: set[str] = set()
    for group_number, (hash_value, items) in enumerate((item for item in groups.items() if len(item[1]) > 1), start=1):
        canonical = choose_best_chunk(items)
        group_id = f"chunk-{group_number:06d}"
        for doc, chunk, cleaned in items:
            duplicate = chunk.qdrant_point_id != canonical[1].qdrant_point_id
            if duplicate:
                duplicate_point_ids.add(chunk.qdrant_point_id)
            rows.append({
                "duplicate_chunk_group_id": group_id,
                "content_hash": hash_value,
                "chunk_id": chunk.qdrant_point_id,
                "document_id": doc.id,
                "document_name": doc.original_filename,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "recommended_action": "DUPLICATE" if duplicate else "KEEP_CANONICAL",
                "canonical_chunk_id": canonical[1].qdrant_point_id,
                "canonical_document_id": canonical[0].id,
                "cleaned_word_count": len(cleaned.split()),
            })
    return rows, duplicate_point_ids


def choose_best_chunk(items: list[tuple[DocumentRecord, ChunkRecord, str]]) -> tuple[DocumentRecord, ChunkRecord, str]:
    return sorted(items, key=lambda item: (item[1].quality_score, len(item[2]), item[0].trust_level == "high"), reverse=True)[0]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def document_audit_rows(docs: list[DocumentRecord], duplicate_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    audit_rows: list[dict[str, Any]] = []
    removal_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    for doc in docs:
        classification, reasons = classify_document(doc, duplicate_ids)
        inferred_language, language_reasons = infer_language(doc)
        metadata_issues = document_metadata_issues(doc)
        row = {
            "document_id": doc.id,
            "classification": classification,
            "reasons": "; ".join(reasons),
            "canonical_title": canonical_title(doc),
            "normalized_title": normalize_title(doc.title or doc.original_filename),
            "original_filename": doc.original_filename,
            "storage_path": doc.storage_path,
            "status": doc.status,
            "chunk_count": len(doc.chunks),
            "quality_average": average_quality(doc),
            "noisy_chunk_ratio": round(noisy_chunk_ratio(doc), 4),
            "document_type": doc.document_type,
            "inferred_document_type": infer_document_type(doc),
            "dental_specialty": infer_specialty(doc),
            "difficulty_level": infer_difficulty(doc),
            "language": doc.language,
            "inferred_language": inferred_language,
            "trust_level": doc.trust_level,
            "recommended_trust_level": infer_trust(doc, classification),
            "review_status": doc.review_status,
            "recommended_review_status": "reviewed" if classification == "KEEP" else "unreviewed",
            "file_hash": doc.file_hash,
            "content_fingerprint": text_fingerprint(doc.chunks),
            "ocr_used": doc.ocr_used,
            "author": doc.author_or_source,
            "publisher": "",
            "publication_year": doc.publication_year or "",
            "edition": doc.edition,
            "extraction_method": "ocr" if doc.ocr_used else "pdf_text",
        }
        audit_rows.append(row)
        if classification in {"QUARANTINE", "REMOVE_CANDIDATE", "DUPLICATE"}:
            removal_rows.append(row)
        if metadata_issues or language_reasons:
            metadata_rows.append({
                "document_id": doc.id,
                "original_filename": doc.original_filename,
                "issues": "; ".join(metadata_issues + language_reasons),
                "stored_language": doc.language,
                "inferred_language": inferred_language,
                "stored_trust_level": doc.trust_level,
                "recommended_trust_level": row["recommended_trust_level"],
                "stored_review_status": doc.review_status,
                "recommended_review_status": row["recommended_review_status"],
            })
    return audit_rows, removal_rows, metadata_rows


def chunk_cleaning_rows(docs: list[DocumentRecord]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    noisy_removed = 0
    for doc in docs:
        for chunk in doc.chunks:
            cleaned = clean_chunk_text(chunk.text)
            locally_noisy, local_reasons, local_score = assess_text_quality(cleaned)
            reasons = sorted(set(chunk.noise_reasons + local_reasons))
            is_noisy = bool(chunk.is_noisy or locally_noisy)
            if is_noisy:
                noisy_removed += 1
            rows.append({
                "chunk_id": chunk.qdrant_point_id,
                "document_id": doc.id,
                "canonical_document_title": canonical_title(doc),
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "dental_specialty": infer_specialty(doc),
                "topic": "",
                "difficulty_level": infer_difficulty(doc),
                "language": infer_language(doc)[0],
                "trust_level": infer_trust(doc, "KEEP"),
                "quality_score": min(chunk.quality_score, local_score),
                "is_noisy": is_noisy,
                "noise_reasons": "; ".join(reasons),
                "review_status": "review" if is_noisy else "keep",
                "content_hash": content_hash(cleaned),
                "original_word_count": len(chunk.text.split()),
                "cleaned_word_count": len(cleaned.split()),
                "cleaned_preview": cleaned[:500],
            })
    return rows, noisy_removed


def cleanup_summary(
    docs: list[DocumentRecord],
    audit_rows: list[dict[str, Any]],
    duplicate_doc_rows: list[dict[str, Any]],
    duplicate_chunk_rows_value: list[dict[str, Any]],
    noisy_chunks_removed: int,
) -> dict[str, Any]:
    counts = Counter(row["classification"] for row in audit_rows)
    exact_groups = {row["duplicate_group_id"] for row in duplicate_doc_rows if row["match_type"] == "exact_file_hash"}
    near_groups = {row["duplicate_group_id"] for row in duplicate_doc_rows if row["match_type"] == "near_duplicate"}
    total_chunks = sum(len(doc.chunks) for doc in docs)
    duplicate_chunks_removed = sum(1 for row in duplicate_chunk_rows_value if row["recommended_action"] == "DUPLICATE")
    return {
        "mode": "dry_run",
        "total_documents": len(docs),
        "keep_count": counts["KEEP"],
        "review_count": counts["REVIEW"],
        "quarantine_count": counts["QUARANTINE"],
        "duplicate_document_count": counts["DUPLICATE"],
        "remove_candidate_count": counts["REMOVE_CANDIDATE"],
        "exact_duplicate_group_count": len(exact_groups),
        "near_duplicate_group_count": len(near_groups),
        "useless_document_count": counts["QUARANTINE"] + counts["REMOVE_CANDIDATE"],
        "total_chunks_before_cleaning": total_chunks,
        "noisy_chunks_removed": noisy_chunks_removed,
        "duplicate_chunks_removed": duplicate_chunks_removed,
        "clean_chunks_remaining": max(0, total_chunks - noisy_chunks_removed - duplicate_chunks_removed),
    }


def print_summary(summary: dict[str, Any]) -> None:
    labels = [
        ("total_documents", "total documents"),
        ("keep_count", "keep count"),
        ("review_count", "review count"),
        ("quarantine_count", "quarantine count"),
        ("exact_duplicate_group_count", "exact duplicate count"),
        ("near_duplicate_group_count", "near-duplicate count"),
        ("useless_document_count", "useless document count"),
        ("total_chunks_before_cleaning", "total chunks before cleaning"),
        ("noisy_chunks_removed", "noisy chunks removed"),
        ("duplicate_chunks_removed", "duplicate chunks removed"),
        ("clean_chunks_remaining", "clean chunks remaining"),
    ]
    for key, label in labels:
        print(f"{label}: {summary.get(key, 0)}")
