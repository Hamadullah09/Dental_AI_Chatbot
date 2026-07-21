from __future__ import annotations

import time

from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


def estimate_confidence(state: AgentState) -> AgentState:
    start = time.perf_counter()

    chunks = state.reranked_chunks or state.retrieved_chunks
    sources_count = len(state.sources)

    if not chunks and not sources_count:
        state.confidence_level = "low"
        state.confidence_score = 0.1
        state.explainability_notes.append("No relevant sources found in knowledge base")
        state.add_trace("confidence_estimator", "completed", "Low: no sources")
        return state

    avg_score = 0.0
    high_quality = 0

    if chunks:
        scores = []
        for c in chunks:
            rerank = c.get("rerank_score", 0) or 0
            vector = c.get("vector_score", 0) or 0
            keyword = c.get("keyword_score", 0) or 0
            combined = rerank * 0.5 + vector * 0.3 + keyword * 0.2
            scores.append(combined)
            if rerank > 0.7 or vector > 0.8:
                high_quality += 1

        avg_score = sum(scores) / len(scores) if scores else 0

    source_coverage = min(sources_count / 3, 1.0)
    quality_factor = min(high_quality / max(len(chunks), 1), 1.0)

    intent_factor = 1.0
    if state.intent == "emergency":
        intent_factor = 0.8
    elif state.intent == "image_analysis":
        has_visuals = bool(state.reranked_visuals or state.retrieved_visuals)
        intent_factor = 0.9 if has_visuals else 0.4

    state.confidence_score = (avg_score * 0.4 + source_coverage * 0.25 + quality_factor * 0.25) * intent_factor
    state.confidence_score = max(0.0, min(1.0, state.confidence_score))

    if state.confidence_score >= 0.75:
        state.confidence_level = "high"
    elif state.confidence_score >= 0.4:
        state.confidence_level = "medium"
    else:
        state.confidence_level = "low"

    if state.confidence_level == "low":
        state.explainability_notes.append("Limited high-quality evidence found — answer may not fully address the question")
    elif state.confidence_level == "medium":
        state.explainability_notes.append("Moderate evidence available — consider consulting a professional for confirmation")

    source_types_found = set()
    for s in state.sources[:5]:
        if hasattr(s, "source_type"):
            source_types_found.add(s.source_type)
        elif isinstance(s, dict):
            st = s.get("source_type", "")
            if st:
                source_types_found.add(st)

    if source_types_found:
        type_labels = []
        for st in sorted(source_types_found):
            if st == "web":
                type_labels.append("Trusted Web Sources")
            elif st == "pdf":
                type_labels.append("Dental Textbooks / Guidelines")
            else:
                type_labels.append(st.capitalize())
        state.explainability_notes.append(f"Sources: {', '.join(type_labels)}")

    duration_ms = (time.perf_counter() - start) * 1000
    state.add_trace("confidence_estimator", "completed", f"{state.confidence_level} ({state.confidence_score:.2f})", duration_ms)
    return state
