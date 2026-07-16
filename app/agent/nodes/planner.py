from __future__ import annotations

import time
import re
from typing import Any, Literal

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
    "orthodontic", "braces", "aligner",     "veneer", "scaling",
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

DIRECT_ANSWER_KEYWORDS = {
    "what is", "define", "who is", "when was", "how old",
    "hello", "hi", "thanks", "thank you", "goodbye", "bye",
}

CONVERSATIONAL_PATTERNS = (
    r"hi",
    r"hello",
    r"hey",
    r"good morning",
    r"good evening",
    r"thanks",
    r"thank you",
    r"bye",
    r"goodbye",
)


def _contains_keyword(question_lower: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in question_lower
    return re.search(rf"\b{re.escape(keyword)}\b", question_lower) is not None


def _is_conversational_query(question_lower: str) -> bool:
    normalized = re.sub(r"\s+", " ", question_lower).strip(" .,!?:;\n\t")
    if not normalized:
        return False
    return any(re.fullmatch(pattern, normalized) for pattern in CONVERSATIONAL_PATTERNS)


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
    elif any(_contains_keyword(question_lower, phrase) for phrase in DIRECT_ANSWER_KEYWORDS):
        state.intent = "direct"
    else:
        state.intent = "general"

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("intent_detector", "completed", f"Intent: {state.intent}", duration_ms)
    return state


def can_answer_directly(state: AgentState) -> Literal["yes", "no"]:
    if state.intent == "direct":
        return "yes"
    if state.intent == "emergency":
        return "no"
    question_lower = state.question.lower()
    if _is_conversational_query(question_lower):
        return "yes"
    return "no"


def generate_direct_answer(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    question_lower = re.sub(r"\s+", " ", state.question.lower()).strip(" .,!?:;\n\t")
    if question_lower in {"hello", "hi", "hey", "good morning", "good evening"}:
        state.answer = "Hello! I'm DentalGPT, your AI dental assistant. How can I help you today?"
    elif question_lower in {"thanks", "thank you"}:
        state.answer = "You're welcome! Feel free to ask if you have more dental questions."
    elif question_lower in {"bye", "goodbye"}:
        state.answer = "Goodbye! Take care of your dental health!"
    else:
        try:
            from app.services.rag import RAGService

            rag = RAGService()
            fallback = rag.generate_general_fallback_answer(state.question, user_role=state.user_role)
            state.answer = fallback or settings.medical_disclaimer
            state.answer_mode = "general_fallback" if fallback else "insufficient_evidence"
            state.sources = []
            duration_ms = (time.perf_counter() - start) * 1000
            state.add_trace("direct_answer", "completed", f"Mode: {state.answer_mode}", duration_ms)
            return state
        except Exception:
            state.answer = settings.medical_disclaimer

    state.answer_mode = "conversational"
    state.sources = []
    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("direct_answer", "completed", f"Mode: {state.answer_mode}", duration_ms)
    return state


def has_enough_evidence(state: AgentState) -> Literal["yes", "no"]:
    if state.intent == "visual" and state.retrieved_visuals:
        return "yes"
    if not state.retrieved_chunks:
        return "no"
    if state.intent == "emergency":
        return "yes"
    good_chunks = [c for c in state.retrieved_chunks if c.get("rerank_score", 0) > 0.5 or c.get("vector_score", 0) > 0.7]
    if len(good_chunks) >= 2:
        return "yes"
    if len(state.retrieved_chunks) >= 3:
        return "yes"
    return "no"


def search_more(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    state.retry_count += 1
    if state.retry_count > state.max_retries:
        try:
            from app.services.rag import RAGService
            rag = RAGService()
            fallback = rag.generate_general_fallback_answer(state.question, user_role=state.user_role)
            if fallback:
                state.answer = fallback
                state.answer_mode = "general_fallback"
                duration_ms = (time.perf_counter() - start) * 1000
                state.add_trace("search_more", "exhausted_fallback", "General fallback via LLM", duration_ms)
                return state
        except Exception:
            pass
        state.answer = (
            "I found limited information on this topic in my dental knowledge base. "
            "I recommend consulting a dental professional for accurate diagnosis and treatment. "
            f"{settings.medical_disclaimer}"
        )
        state.answer_mode = "insufficient_evidence"
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("search_more", "exhausted", "Max retries reached", duration_ms)
        return state

    try:
        from app.services.rag import RAGService
        rag = RAGService()
        query = state.rewritten_query or state.question
        top_k = (state.top_k or settings.retrieval_top_k) + (state.retry_count * 3)

        new_chunks = rag.retrieve(query, top_k=top_k, filters=state.filters)
        existing_ids = {c.get("citation", {}).get("chunk_index") for c in state.retrieved_chunks}
        for chunk in new_chunks:
            idx = chunk.citation.chunk_index
            if idx not in existing_ids:
                state.retrieved_chunks.append({
                    "text": chunk.text,
                    "citation": {
                        "source_type": chunk.citation.source_type,
                        "document_id": chunk.citation.document_id,
                        "document_name": chunk.citation.document_name,
                        "page_number": chunk.citation.page_number,
                        "chunk_index": chunk.citation.chunk_index,
                        "score": chunk.citation.score,
                    },
                    "vector_score": chunk.vector_score,
                    "keyword_score": chunk.keyword_score,
                    "rerank_score": chunk.rerank_score,
                })

        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("search_more", "completed", f"Added chunks, total: {len(state.retrieved_chunks)}", duration_ms)

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("search_more", "error", str(exc), duration_ms)

    return state


def respond_with_uncertainty(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    try:
        from app.services.rag import RAGService
        rag = RAGService()
        fallback = rag.generate_general_fallback_answer(state.question, user_role=state.user_role)
        if fallback:
            state.answer = fallback
            state.answer_mode = "general_fallback"
            duration_ms = (time.perf_counter() - start) * 1000
            state.add_trace("uncertainty_responder", "completed", "General fallback via LLM", duration_ms)
            return state
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        state.add_trace("uncertainty_responder", "fallback_error", str(exc), duration_ms)

    state.answer = (
        "I don't have sufficient information in my dental knowledge base to answer this question accurately. "
        "This topic may require specialized clinical knowledge or the latest research. "
        "I recommend consulting a dental professional for accurate information. "
        f"{settings.medical_disclaimer}"
    )
    state.answer_mode = "insufficient_evidence"
    state.add_trace("uncertainty_responder", "completed", "Insufficient evidence")
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

    import re
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

    state.rewritten_query = variants[0] if variants else question
    state.query_variants = variants[:settings.multi_query_max_variants]

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("query_rewriter", "completed", f"{len(variants)} variants", duration_ms)
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
        if isinstance(source, dict):
            doc_name = source.get("document_name", "Unknown")
        else:
            doc_name = getattr(source, "document_name", "Unknown")
        if doc_name and doc_name != "Unknown":
            validated_sources.append(source)

    state.sources = validated_sources

    if state.retrieved_chunks and not state.sources:
        for chunk in state.retrieved_chunks[:3]:
            citation = chunk.get("citation", {})
            state.sources.append({
                "source_type": citation.get("source_type", "pdf"),
                "document_id": citation.get("document_id"),
                "document_name": citation.get("document_name", "Unknown"),
                "page_number": citation.get("page_number"),
                "chunk_index": citation.get("chunk_index"),
                "score": citation.get("score"),
            })

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
    if state.error is None:
        return state
    if state.retry_count < state.max_retries:
        state.retry_count += 1
        state.error = None
        state.add_trace("error_recovery", "retrying", f"Retry {state.retry_count}/{state.max_retries}")
    else:
        state.answer = "I encountered an issue processing your request. Please try again or contact support."
        state.answer_mode = "error"
        state.add_trace("error_recovery", "failed", state.error)
    return state
