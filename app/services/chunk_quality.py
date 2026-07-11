import re
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ChunkQuality:
    is_noisy: bool
    noise_reasons: list[str]
    quality_score: float


QUESTIONNAIRE_TERMS = [
    "never",
    "very often",
    "fairly often",
    "sometimes",
    "don't know",
    "don’t know",
    "dont know",
    "do not know",
]

FORM_TERMS = [
    "put a tick",
    "put a cross",
    "tick/cross",
    "tick or cross",
    "how often do you",
    "clean your teeth",
    "questionnaire",
    "survey",
    "interviewer",
    "respondent",
]

REFERENCE_HEADINGS = [
    "references",
    "bibliography",
    "index",
    "annex",
    "appendix",
]


def assess_chunk_quality(text: str) -> ChunkQuality:
    normalized = normalize_for_quality(text)
    lower = normalized.lower()
    reasons: list[str] = []
    score = 1.0

    word_count = len(re.findall(r"\b[\w'-]+\b", normalized))
    if word_count < 35:
        reasons.append("very_short_text")
        score -= 0.35

    if "/h17040" in lower or "h17040" in lower:
        reasons.append("who_form_artifact_h17040")
        score -= 0.55

    form_hits = [term for term in FORM_TERMS if term in lower]
    if form_hits:
        reasons.append("questionnaire_or_form_text")
        score -= 0.35 + min(len(form_hits), 3) * 0.08

    scale_hits = [term for term in QUESTIONNAIRE_TERMS if term in lower]
    if len(scale_hits) >= 3:
        reasons.append("questionnaire_scale_options")
        score -= 0.35

    if has_reference_heading(lower):
        reasons.append("reference_index_or_bibliography")
        score -= 0.3

    if looks_like_table_of_contents(normalized):
        reasons.append("table_of_contents_page")
        score -= 0.45

    if looks_like_references_only(normalized):
        reasons.append("references_only_page")
        score -= 0.45

    symbol_ratio = symbol_or_digit_ratio(normalized)
    if symbol_ratio > 0.38:
        reasons.append("mostly_symbols_numbers_or_table_artifacts")
        score -= 0.4

    if looks_like_table_or_form(normalized):
        reasons.append("table_or_form_layout")
        score -= 0.3

    if looks_like_ocr_garbage(normalized):
        reasons.append("ocr_or_layout_garbage")
        score -= 0.45

    if repeated_word_ratio(normalized) > 0.18:
        reasons.append("repeated_text")
        score -= 0.25

    repeated_line_ratio = repeated_short_line_ratio(text)
    if repeated_line_ratio > 0.35:
        reasons.append("repeated_headers_or_footers")
        score -= 0.25

    score = max(0.0, min(1.0, round(score, 3)))
    return ChunkQuality(
        is_noisy=score < 0.6 or bool(
            {
                "who_form_artifact_h17040",
                "questionnaire_scale_options",
                "table_of_contents_page",
                "references_only_page",
            }
            & set(reasons)
        ),
        noise_reasons=reasons,
        quality_score=score,
    )


def normalize_for_quality(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def symbol_or_digit_ratio(text: str) -> float:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return 1.0
    noisy_chars = sum(1 for char in compact if not char.isalpha())
    return noisy_chars / len(compact)


def has_reference_heading(lower_text: str) -> bool:
    stripped = lower_text.strip(" .:-")
    if stripped in REFERENCE_HEADINGS:
        return True
    return any(re.search(rf"\b{re.escape(heading)}\b\s*(\d+)?\s*$", stripped) for heading in REFERENCE_HEADINGS)


def looks_like_table_or_form(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    short_lines = sum(1 for line in lines if len(line) < 55)
    option_lines = sum(1 for line in lines if re.search(r"\b(yes|no|never|often|sometimes|male|female|tick|cross)\b", line, re.I))
    numeric_lines = sum(1 for line in lines if re.search(r"(^|\s)[A-Z]?\d+([.)]|\s)", line))
    return (short_lines / len(lines) > 0.65 and option_lines >= 2) or numeric_lines >= 4


def looks_like_table_of_contents(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return False
    heading = lines[0].lower().strip(" .:-")
    toc_lines = sum(1 for line in lines if re.search(r"\.{3,}\s*\d+$|^\d+(\.\d+)*\s+.+\s+\d+$", line))
    return heading in {"contents", "table of contents"} and toc_lines >= 3


def looks_like_references_only(text: str) -> bool:
    lower = text.lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    heading = lines[0].lower().strip(" .:-")
    citation_hits = len(re.findall(r"\bet al\.|\bdoi\b|https?://|\bisbn\b|\bvol\.|\bpp\.|\(\d{4}\)", lower))
    if heading in {"references", "bibliography"} and citation_hits >= 3:
        return True
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", text)
    return citation_hits >= 8 and len(words) < 240


def looks_like_ocr_garbage(text: str) -> bool:
    lower = text.lower()
    suspicious_patterns = [
        r"~\s*[a-z]{1,4}",
        r"\"{2,}",
        r"[a-z]\s*[~<>]\s*[a-z]",
        r"\bfig\.?\s*(er|if|and|,)",
        r"\bcourtesy\s+dr\.",
    ]
    if any(re.search(pattern, lower) for pattern in suspicious_patterns):
        return True

    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if len(words) < 30:
        return False
    very_short = sum(1 for word in words if len(word) <= 2)
    consonant_heavy = sum(1 for word in words if len(word) >= 5 and not re.search(r"[aeiouAEIOU]", word))
    return very_short / len(words) > 0.35 or consonant_heavy >= 4


def repeated_short_line_ratio(text: str) -> float:
    lines = [line.strip().lower() for line in text.splitlines() if 4 <= len(line.strip()) <= 80]
    if len(lines) < 4:
        return 0.0
    repeated = len(lines) - len(set(lines))
    return repeated / len(lines)


def repeated_word_ratio(text: str) -> float:
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z'-]+", text)]
    if len(words) < 30:
        return 0.0
    repeated_runs = 0
    for previous, current in zip(words, words[1:]):
        if previous == current:
            repeated_runs += 1
    return repeated_runs / len(words)


def is_form_or_survey_question(question: str) -> bool:
    question_l = question.lower()
    patterns = [
        r"\bsurvey\b",
        r"\bquestionnaire\b",
        r"\bforms?\b",
        r"\bassessment\s+forms?\b",
        r"\boral\s+health\s+assessment\b",
        r"\btick\b",
        r"\bcross\b",
        r"\bwho\s+oral\s+health\s+survey\b",
    ]
    return any(re.search(pattern, question_l) for pattern in patterns)
