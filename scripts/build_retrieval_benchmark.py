from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, init_db
from app.models import Document, DocumentChunk, DocumentVisual


DEFAULT_OUTPUT = Path("docs") / "retrieval_benchmark_200.jsonl"
MAX_PER_DOCUMENT = 12


QUESTION_TEMPLATES = [
    "What does the uploaded evidence say about {topic}?",
    "Summarize the key point about {topic}.",
    "What clinical concept is described in the section on {topic}?",
    "Which evidence is present in the chunk about {topic}?",
    "Explain the relevant dental point about {topic}.",
    "What should a dental student remember about {topic}?",
    "What is the main finding or teaching point for {topic}?",
    "How is {topic} described in the uploaded dental reference?",
]


TOPIC_PATTERNS = [
    (r"\bdental caries\b|\bcaries\b|\btooth decay\b", "dental caries"),
    (r"\bperiodontal\b|\bgingivitis\b|\bperiodontitis\b", "periodontal disease"),
    (r"\borthodontic\b|\bmalocclusion\b|\bbracket\b|\baligner\b", "orthodontic treatment"),
    (r"\bimplant\b|\banchorage\b", "implants and anchorage"),
    (r"\bendodontic\b|\broot canal\b|\bpulp\b", "endodontic treatment"),
    (r"\bmaxillofacial\b|\boral surgery\b|\borthognathic\b", "oral and maxillofacial surgery"),
    (r"\bcephalometric\b|\bcephalometry\b", "cephalometrics"),
    (r"\bocclusion\b|\bocclusal\b", "occlusion"),
    (r"\bradiograph\b|\bradiology\b|\bcbct\b|\bx-ray\b", "dental radiology"),
    (r"\bfluoride\b|\bprevention\b|\boral hygiene\b", "prevention and oral hygiene"),
]

DENTAL_KEY_TERMS = [
    "caries",
    "enamel",
    "dentin",
    "fluoride",
    "plaque",
    "periodontal",
    "gingivitis",
    "periodontitis",
    "orthodontic",
    "malocclusion",
    "bracket",
    "aligner",
    "implant",
    "anchorage",
    "endodontic",
    "pulp",
    "occlusion",
    "radiograph",
    "cephalometric",
    "maxillofacial",
    "orthognathic",
    "mandibular",
    "maxillary",
    "surgery",
    "prevention",
    "hygiene",
]

LOW_VALUE_SECTION_TITLES = {
    "article info",
    "article info abstract",
    "abstract",
    "abstract:",
    "introduction",
    "definition",
    "assessment",
    "discussion",
    "conclusion",
    "conclusions",
    "references",
}

LOW_VALUE_SECTION_FRAGMENTS = {
    "abstract",
    "article info",
    "author",
    "background",
    "bibliography",
    "clinical significance",
    "conflict",
    "conclusion",
    "correspondence",
    "copyright",
    "hypotheses",
    "introduction",
    "journal",
    "management:",
    "material and methods",
    "materials and methods",
    "methodology",
    "objective",
    "objectives",
    "references",
    "received",
    "trial design",
}

LOW_VALUE_EXPECTED_TERMS = {
    "available",
    "abstract",
    "adverse",
    "amount",
    "appliance",
    "appliances",
    "article",
    "author",
    "authors",
    "background",
    "because",
    "before",
    "being",
    "certain",
    "copyright",
    "described",
    "department",
    "development",
    "email",
    "evidence",
    "figure",
    "found",
    "given",
    "hypersensitivity",
    "include",
    "including",
    "increase",
    "increased",
    "increases",
    "increasing",
    "journal",
    "manuscript",
    "material",
    "materials",
    "method",
    "methods",
    "modern",
    "nature",
    "objective",
    "often",
    "present",
    "presence",
    "population",
    "provided",
    "promotes",
    "publisher",
    "received",
    "reported",
    "result",
    "results",
    "review",
    "showed",
    "shown",
    "significant",
    "studies",
    "suggest",
    "suggested",
    "suggests",
    "systemic",
    "table",
    "therefore",
    "typically",
    "using",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a categorized retrieval benchmark from retained text chunks and visuals.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSONL benchmark output path.")
    parser.add_argument("--limit", type=int, default=200, help="Number of benchmark questions to create.")
    parser.add_argument("--text-count", type=int, default=110, help="Target text-only retrieval cases.")
    parser.add_argument("--visual-count", type=int, default=50, help="Target figure/diagram/image visual cases.")
    parser.add_argument("--table-count", type=int, default=20, help="Target table/chart visual cases.")
    parser.add_argument("--negative-count", type=int, default=20, help="Target cases where no visual should appear.")
    parser.add_argument("--min-quality", type=float, default=0.65, help="Minimum chunk quality score.")
    args = parser.parse_args()

    init_db()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = build_cases(
        limit=args.limit,
        min_quality=args.min_quality,
        text_count=args.text_count,
        visual_count=args.visual_count,
        table_count=args.table_count,
        negative_count=args.negative_count,
    )
    with output.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} benchmark cases to {output}")


def build_cases(
    limit: int,
    min_quality: float,
    text_count: int,
    visual_count: int,
    table_count: int,
    negative_count: int,
) -> list[dict]:
    cases: list[dict] = []
    seen_questions: set[str] = set()
    with SessionLocal() as db:
        rows = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(DocumentChunk.is_noisy.is_(False))
            .filter(DocumentChunk.quality_score >= min_quality)
            .order_by(DocumentChunk.quality_score.desc(), DocumentChunk.created_at.desc())
            .limit(max(limit * 30, 3000))
            .all()
        )
        chunks = balanced_rows(rows)

        for chunk, document in chunks:
            if not is_good_benchmark_chunk(chunk, document):
                continue
            topic = infer_topic(chunk, document)
            expected_terms = expected_terms_for(chunk.text, topic)
            if len(expected_terms) < 2:
                continue
            question = make_question(topic, chunk, document, expected_terms, len(cases))
            if question in seen_questions:
                question = f"{question} Include evidence around {', '.join(expected_terms[:2])}."
            if question in seen_questions:
                continue
            seen_questions.add(question)
            cases.append(
                {
                    "id": f"bench-{len(cases) + 1:03d}",
                    "case_type": "text",
                    "question": question,
                    "expect_visual": False,
                    "expected_document_id": document.id,
                    "expected_chunk_id": chunk.qdrant_point_id,
                    "expected_chunk_index": chunk.chunk_index,
                    "expected_page_number": chunk.page_number,
                    "expected_terms": expected_terms,
                    "canonical_document_title": chunk.canonical_document_title
                    or document.canonical_title
                    or document.title
                    or document.original_filename,
                    "section_title": chunk.section_title or "",
                    "chapter_title": chunk.chapter_title or "",
                    "topic": topic,
                    "dental_specialty": chunk.dental_specialty or document.dental_specialty or document.specialty,
                    "difficulty_level": chunk.difficulty_level or document.difficulty_level,
                    "trust_level": chunk.trust_level or document.trust_level.value,
                    "review_status": chunk.review_status or document.review_status.value,
                }
            )
            if len([case for case in cases if case["case_type"] == "text"]) >= text_count:
                break
        cases.extend(build_visual_cases(db, visual_count, case_type="visual", seen_questions=seen_questions))
        cases.extend(build_visual_cases(db, table_count, case_type="table_chart", seen_questions=seen_questions))
        cases.extend(build_negative_cases(negative_count, seen_questions))

        if len(cases) < limit:
            for chunk, document in chunks:
                if len(cases) >= limit:
                    break
                if not is_good_benchmark_chunk(chunk, document):
                    continue
                topic = infer_topic(chunk, document)
                expected_terms = expected_terms_for(chunk.text, topic)
                if len(expected_terms) < 2:
                    continue
                question = make_question(topic, chunk, document, expected_terms, len(cases))
                if question in seen_questions:
                    continue
                seen_questions.add(question)
                cases.append(
                    {
                        "id": f"bench-{len(cases) + 1:03d}",
                        "case_type": "text",
                        "question": question,
                        "expect_visual": False,
                        "expected_document_id": document.id,
                        "expected_chunk_id": chunk.qdrant_point_id,
                        "expected_chunk_index": chunk.chunk_index,
                        "expected_page_number": chunk.page_number,
                        "expected_terms": expected_terms,
                        "canonical_document_title": chunk.canonical_document_title
                        or document.canonical_title
                        or document.title
                        or document.original_filename,
                        "section_title": chunk.section_title or "",
                        "chapter_title": chunk.chapter_title or "",
                        "topic": topic,
                        "dental_specialty": chunk.dental_specialty or document.dental_specialty or document.specialty,
                        "difficulty_level": chunk.difficulty_level or document.difficulty_level,
                        "trust_level": chunk.trust_level or document.trust_level.value,
                        "review_status": chunk.review_status or document.review_status.value,
                    }
                )
    return cases


def build_visual_cases(db, limit: int, case_type: str, seen_questions: set[str]) -> list[dict]:
    if limit <= 0:
        return []
    visual_types = ["table", "chart"] if case_type == "table_chart" else ["figure", "diagram", "flowchart", "page_snapshot", "unknown"]
    rows = (
        db.query(DocumentVisual)
        .filter(DocumentVisual.quality_score >= 0.55)
        .filter(DocumentVisual.visual_type.in_(visual_types))
        .order_by(DocumentVisual.quality_score.desc(), DocumentVisual.created_at.desc())
        .limit(limit * 8)
        .all()
    )
    cases: list[dict] = []
    for visual in rows:
        topic = visual_topic(visual)
        question = visual_question(visual, topic, case_type)
        if question in seen_questions:
            continue
        seen_questions.add(question)
        cases.append(
            {
                "id": "",
                "case_type": case_type,
                "question": question,
                "expect_visual": True,
                "expected_visual_id": visual.visual_id,
                "expected_document_id": visual.document_id,
                "expected_page_number": visual.page_number,
                "expected_terms": expected_terms_for(visual.searchable_text if hasattr(visual, "searchable_text") else searchable_visual_text(visual), topic),
                "visual_type": visual.visual_type,
                "topic": topic,
            }
        )
        if len(cases) >= limit:
            break
    for index, case in enumerate(cases, start=1):
        case["id"] = f"bench-{case_type}-{index:03d}"
    return cases


def build_negative_cases(limit: int, seen_questions: set[str]) -> list[dict]:
    templates = [
        "Answer without showing a figure: what general topic is discussed in the uploaded references?",
        "Give a text-only summary of the uploaded dental evidence about prevention.",
        "What does the text say about clinical decision making? Do not show images unless directly necessary.",
        "Summarize the text evidence only for this dental concept.",
        "What does the uploaded text explain? Avoid figures unless the question asks for one.",
    ]
    cases: list[dict] = []
    for index in range(limit):
        question = templates[index % len(templates)]
        if question in seen_questions:
            question = f"{question} Case {index + 1}."
        seen_questions.add(question)
        cases.append(
            {
                "id": f"bench-negative-{index + 1:03d}",
                "case_type": "negative_no_visual",
                "question": question,
                "expect_visual": False,
                "expected_terms": [],
                "expected_sources": [],
            }
        )
    return cases


def visual_question(visual: DocumentVisual, topic: str, case_type: str) -> str:
    descriptor = visual.caption_text or visual.generated_description or topic
    descriptor = re.sub(r"\s+", " ", descriptor).strip()
    if len(descriptor) > 110:
        descriptor = descriptor[:110].rsplit(" ", 1)[0]
    if case_type == "table_chart":
        return f"Which table or chart is relevant to {topic}? Use the visual from the uploaded document if available."
    return f"Show the relevant figure or diagram for {topic}. Focus on {descriptor}."


def visual_topic(visual: DocumentVisual) -> str:
    text = searchable_visual_text(visual)
    for pattern, topic in TOPIC_PATTERNS:
        if re.search(pattern, text.lower()):
            return topic
    clinical_terms = [term for term in DENTAL_KEY_TERMS if re.search(rf"\b{re.escape(term)}\b", text.lower())]
    if clinical_terms:
        return " ".join(clinical_terms[:3])
    clean_words = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z-]{4,}", text.lower())
        if is_clean_expected_term(term)
    ]
    return " ".join(clean_words[:4]) or visual.visual_type.replace("_", " ")


def searchable_visual_text(visual: DocumentVisual) -> str:
    return " ".join(
        str(value or "")
        for value in [
            visual.caption_text,
            visual.nearby_text,
            visual.generated_description,
            visual.document_name,
            visual.visual_type,
        ]
    )


def balanced_rows(rows: list[tuple[DocumentChunk, Document]]) -> list[tuple[DocumentChunk, Document]]:
    grouped: dict[str, list[tuple[DocumentChunk, Document]]] = {}
    for chunk, document in rows:
        grouped.setdefault(document.id, []).append((chunk, document))
    balanced: list[tuple[DocumentChunk, Document]] = []
    for group in grouped.values():
        balanced.extend(group[:MAX_PER_DOCUMENT])
    return sorted(balanced, key=lambda item: (item[1].original_filename.lower(), item[0].chunk_index))


def is_good_benchmark_chunk(chunk: DocumentChunk, document: Document) -> bool:
    text = " ".join((chunk.text or "").split())
    lower = text.lower()
    title = f"{chunk.section_title or ''} {chunk.chapter_title or ''} {document.original_filename or ''}".lower()
    if len(text.split()) < 55:
        return False
    if any(term in lower[:220] for term in ["references", "bibliography", "index", "table of contents"]):
        return False
    if any(term in title for term in ["pdfdrive", "z-library", "b-ok", "references", "bibliography", "index"]):
        return False
    section_title = re.sub(r"\s+", " ", (chunk.section_title or "").strip().lower())
    if section_title in LOW_VALUE_SECTION_TITLES:
        return False
    if any(fragment in section_title for fragment in LOW_VALUE_SECTION_FRAGMENTS):
        return False
    first_section_word = (chunk.section_title or "").strip().split(" ", 1)[0].lower()
    if first_section_word and len(first_section_word) > 4 and first_section_word in {"pecific", "ative", "fined"}:
        return False
    if len(re.findall(r"\b(?:doi|isbn|et al|journal|vol\.|pp\.)\b", lower)) >= 4:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", lower)
    if not words:
        return False
    broken = [word for word in words if re.search(r"^[a-z]{1,3}(?:tion|ment|ing|ive|al)$", word)]
    if len(broken) / max(len(words), 1) > 0.12:
        return False
    return any(term in lower for term in DENTAL_KEY_TERMS)


def infer_topic(chunk: DocumentChunk, document: Document) -> str:
    stored = chunk.topic or document.topic
    if stored:
        return stored.replace("_", " ")
    text = f"{chunk.section_title or ''} {chunk.text[:900]}".lower()
    for pattern, topic in TOPIC_PATTERNS:
        if re.search(pattern, text):
            return topic
    title = chunk.canonical_document_title or document.canonical_title or document.title or document.original_filename
    return re.sub(r"\s+", " ", Path(title).stem.replace("_", " ")).strip()[:80] or "general dentistry"


def make_question(topic: str, chunk: DocumentChunk, document: Document, expected_terms: list[str], index: int) -> str:
    detail = useful_detail(chunk, document, expected_terms)
    detail = re.sub(r"\s+", " ", detail).strip()
    if len(detail) > 90:
        detail = detail[:90].rsplit(" ", 1)[0]
    template = QUESTION_TEMPLATES[index % len(QUESTION_TEMPLATES)]
    question = template.format(topic=topic)
    if detail and detail.lower() not in question.lower():
        question = f"{question} Focus on {detail}."
    return question


def useful_detail(chunk: DocumentChunk, document: Document, expected_terms: list[str]) -> str:
    return " ".join(expected_terms[:3])


def expected_terms_for(text: str, topic: str) -> list[str]:
    topic_terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z-]{3,}", topic.lower())
        if term not in {"general", "dentistry", "treatment"}
    ]
    clinical_terms = [term for term in DENTAL_KEY_TERMS if re.search(rf"\b{re.escape(term)}\b", text.lower())]
    candidates = topic_terms + clinical_terms + re.findall(r"[A-Za-z][A-Za-z-]{4,}", text[:900].lower())
    stopwords = {
        "about",
        "according",
        "after",
        "also",
        "and",
        "are",
        "been",
        "between",
        "clinical",
        "could",
        "dental",
        "dentistry",
        "from",
        "for",
        "have",
        "has",
        "had",
        "into",
        "may",
        "more",
        "only",
        "oral",
        "patient",
        "patients",
        "should",
        "than",
        "that",
        "their",
        "there",
        "these",
        "this",
        "through",
        "treatment",
        "were",
        "was",
        "when",
        "which",
        "with",
    }
    terms: list[str] = []
    for term in candidates:
        if term in stopwords or len(term) < 4:
            continue
        if term in LOW_VALUE_EXPECTED_TERMS:
            continue
        if not is_clean_expected_term(term):
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= 4:
            break
    return terms


def is_clean_expected_term(term: str) -> bool:
    if len(term) < 4 or len(term) > 24:
        return False
    if re.search(r"\d", term):
        return False
    if term.endswith("-") or term.startswith("-"):
        return False
    bad_fragments = {
        "tion",
        "ment",
        "ive",
        "cial",
        "ated",
        "ology",
        "ferences",
        "pdfdrive",
        "pecific",
        "ative",
        "rossbites",
        "atency",
        "arent",
        "fined",
        "ecades",
    }
    if term in bad_fragments:
        return False
    vowels = sum(1 for char in term if char in "aeiou")
    return vowels >= 1


if __name__ == "__main__":
    main()
