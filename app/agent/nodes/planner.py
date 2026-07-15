from __future__ import annotations

import re
import time
from typing import Any

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYMPTOM_KEYWORDS = {
    "pain", "ache", "swelling", "bleeding", "sensitivity", "toothache",
    "gum", "infection", "pus", "fever", "trismus", "swollen",
}

TREATMENT_KEYWORDS = {
    "treatment", "therapy", "procedure", "surgery", "extraction",
    "root canal", "crown", "bridge", "implant", "filling", "whitening",
    "orthodontic", "braces", "aligner", " veneer", "scaling",
}

EMERGENCY_KEYWORDS = {
    "emergency", "urgent", "knocked out", "fractured", "severe",
    "trauma", "avulsion", "acute", "immediate", "asap",
}

VISUAL_KEYWORDS = {
    "image", "diagram", "chart", "figure", "picture", "photo",
    "illustration", "x-ray", "radiograph", "scan", "visual",
    "show me", "display", "illustrate",
}

ROMAN_URDU_INDICATORS = {
    "kya", "hai", "kaise", "kyun", "kaun", "mein", "tum",
    "aap", "yeh", "woh", "se", "ko", "ke", "ki", "ka",
}


def detect_intent(state: AgentState) -> AgentState:
    start = time.perf_counter()
    question_lower = state.question.lower()

    if any(word in question_lower for word in EMERGENCY_KEYWORDS):
        state.intent = "emergency"
    elif any(word in question_lower for word in VISUAL_KEYWORDS):
        state.intent = "visual"
    elif any(word in question_lower for word in TREATMENT_KEYWORDS):
        state.intent = "treatment"
    elif any(word in question_lower for word in SYMPTOM_KEYWORDS):
        state.intent = "symptom"
    elif any(word in question_lower for word in ROMAN_URDU_INDICATORS):
        state.intent = "roman_urdu"
    else:
        state.intent = "general"

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("intent_detector", "completed", f"Intent: {state.intent}", duration_ms)
    logger.info(f"Intent detected: {state.intent} in {duration_ms:.1f}ms")
    return state


def rewrite_query(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    if not settings.enable_query_rewriting:
        state.rewritten_query = state.question
        state.query_variants = [state.question]
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("query_rewriter", "skipped", "Query rewriting disabled", duration_ms)
        return state

    question = state.question.strip()
    variants = [question]

    dental_term_map = {
        r"\btooth\s+ache\b": "dental pain pulpitis",
        r"\bbad\s+breath\b": "halitosis oral odor",
        r"\bhole\s+in\s+tooth\b": "dental caries cavity",
        r"\bgum\s+bleeding\b": "gingival bleeding periodontal",
        r"\bswollen\s+gums\b": "gingival swelling inflammation",
        r"\bloose\s+tooth\b": "tooth mobility periodontal",
        r"\bsensitive\s+teeth\b": "dental sensitivity dentin hypersensitivity",
        r"\byellow\s+teeth\b": "tooth discoloration staining",
        r"\bwisdom\s+tooth\b": "third molar",
        r"\bbraces\b": "orthodontic appliance fixed appliance",
        r"\bpull\s+out\b": "extraction dental extraction",
    }

    expanded = question
    for pattern, replacement in dental_term_map.items():
        if re.search(pattern, expanded, re.IGNORECASE):
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)

    if expanded != question:
        variants.append(expanded)

    if settings.enable_hyde and len(variants) < settings.multi_query_max_variants:
        definition_pattern = r"^(what|how|define|explain|describe|tell\s+me\s+about)\s+"
        if re.match(definition_pattern, question, re.IGNORECASE):
            variants.append(f"Dental clinical definition and explanation of {question.split(None, 3)[-1] if len(question.split()) > 3 else question}")

    state.rewritten_query = variants[0] if variants else question
    state.query_variants = variants[:settings.multi_query_max_variants]

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("query_rewriter", "completed", f"{len(variants)} variants", duration_ms)
    logger.info(f"Query rewritten: {len(variants)} variants in {duration_ms:.1f}ms")
    return state


def build_context(state: AgentState) -> AgentState:
    start = time.perf_counter()

    context_parts = []
    if state.retrieved_chunks:
        for i, chunk in enumerate(state.retrieved_chunks):
            text = chunk.get("text", "")
            citation = chunk.get("citation", {})
            doc_name = citation.get("document_name", "Unknown")
            page = citation.get("page_number", "")
            page_str = f" (p. {page})" if page else ""
            context_parts.append(f"[Source {i+1}: {doc_name}{page_str}]\n{text}")

    if state.search_web and hasattr(state, "web_results"):
        for result in getattr(state, "web_results", []):
            context_parts.append(f"[Web Source: {result.get('title', 'Unknown')}]\n{result.get('content', '')}")

    state.context_text = "\n\n---\n\n".join(context_parts)

    if state.visual_context:
        state.context_text += f"\n\n---\n\n[Visual Context]\n{state.visual_context}"

    if state.memory_context:
        state.context_text = f"[Previous conversation context]\n{state.memory_context}\n\n---\n\n{state.context_text}"

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("context_builder", "completed", f"{len(context_parts)} context blocks", duration_ms)
    return state


def validate_citations(state: AgentState) -> AgentState:
    start = time.perf_counter()

    validated_sources = []
    for source in state.sources:
        if source.document_name and source.document_name != "Unknown":
            validated_sources.append(source)

    state.sources = validated_sources

    if state.retrieved_chunks and not state.sources:
        for chunk in state.retrieved_chunks[:3]:
            citation = chunk.get("citation", {})
            state.sources.append(SourceCitation(
                source_type=citation.get("source_type", "pdf"),
                document_id=citation.get("document_id"),
                document_name=citation.get("document_name", "Unknown"),
                page_number=citation.get("page_number"),
                chunk_index=citation.get("chunk_index"),
                score=citation.get("score"),
            ))

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("citation_validator", "completed", f"{len(state.sources)} validated sources", duration_ms)
    return state


def format_response(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    if not state.answer:
        state.answer = "I apologize, but I was unable to generate a response. Please try rephrasing your question."
        state.answer_mode = "error"

    if not state.disclaimer:
        state.disclaimer = settings.medical_disclaimer

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("response_formatter", "completed", f"Mode: {state.answer_mode}", duration_ms)
    return state


def handle_error(state: AgentState) -> AgentState:
    if state.error and state.retry_count < state.max_retries:
        state.retry_count += 1
        state.error = None
        state.add_trace("error_recovery", "retrying", f"Retry {state.retry_count}/{state.max_retries}")
    elif state.error:
        state.answer = "I encountered an issue processing your request. Please try again or contact support."
        state.answer_mode = "error"
        state.add_trace("error_recovery", "failed", state.error)
    return state
