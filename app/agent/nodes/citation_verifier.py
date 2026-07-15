from __future__ import annotations

import json
import time
from typing import Any

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def verify_citations(state: AgentState) -> AgentState:
    start = time.perf_counter()
    settings = get_settings()

    if not state.answer or not state.retrieved_chunks:
        state.add_trace("citation_verifier", "skipped", "No answer or no chunks")
        return state

    sentences = _split_into_sentences(state.answer)
    verified_sentences = []
    removed_count = 0

    for sentence in sentences:
        if _is_disclaimer_or_formatting(sentence):
            verified_sentences.append(sentence)
            continue

        can_support = _check_citation_support(sentence, state.retrieved_chunks, state.context_text)

        if can_support:
            verified_sentences.append(sentence)
        else:
            removed_count += 1
            logger.debug(f"Citation removed: {sentence[:80]}...")

    if removed_count > 0 and len(verified_sentences) > 3:
        state.answer = " ".join(verified_sentences)
        state.add_trace("citation_verifier", "completed", f"Removed {removed_count} unsupported sentences")
    elif removed_count > 0 and len(verified_sentences) <= 3:
        state.add_trace("citation_verifier", "completed", f"Kept all sentences ({removed_count} flagged but too few remaining)")
    else:
        state.add_trace("citation_verifier", "completed", "All sentences verified")

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(f"Citation verification: {removed_count} removed in {duration_ms:.1f}ms")
    return state


def _split_into_sentences(text: str) -> list[str]:
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def _is_disclaimer_or_formatting(sentence: str) -> bool:
    lower = sentence.lower()
    return any(phrase in lower for phrase in [
        "dental ai", "medical disclaimer", "does not replace",
        "consult", "professional", "disclaimer",
    ]) or sentence.startswith("[") or sentence.startswith("**")


def _check_citation_support(sentence: str, chunks: list[dict], context: str) -> bool:
    sentence_words = set(sentence.lower().split())
    sentence_words = {w for w in sentence_words if len(w) > 3}

    if not sentence_words:
        return True

    context_lower = context.lower()
    matching_words = sum(1 for w in sentence_words if w in context_lower)
    coverage = matching_words / len(sentence_words) if sentence_words else 0

    return coverage >= 0.4
