from __future__ import annotations

import enum
import hashlib
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import RedisCache

if TYPE_CHECKING:
    from app.services.rag import RAGService, RetrievedChunk

logger = get_logger(__name__)


class DegradationTier(enum.StrEnum):
    """Explicit, named retrieval tiers (Phase 1). Each step down is a distinct, logged,
    metered code path rather than an implicit side effect of an exception handler."""

    full_hybrid = "full_hybrid"
    keyword_only = "keyword_only"
    cached_answer = "cached_answer"
    static_degraded = "static_degraded"


def _answer_cache() -> RedisCache:
    settings = get_settings()
    return RedisCache(prefix="degraded_answer_cache", ttl=settings.degraded_answer_cache_ttl_seconds)


def _normalized_question_key(question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def cache_successful_answer(question: str, answer: str, sources: list, visuals: list | None = None) -> None:
    """Called after a normal full_hybrid turn succeeds, so that same/similar questions can
    be served from cache if retrieval later degrades entirely (Qdrant AND Postgres down).
    This is a coarse question-text cache, not full retrieval - documented simplification,
    see docs/GAP_AUDIT_PHASE0.md addendum."""
    try:
        _answer_cache().set(
            _normalized_question_key(question),
            {
                "answer": answer,
                "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in sources],
                "visuals": [v.model_dump() if hasattr(v, "model_dump") else v for v in (visuals or [])],
            },
        )
    except Exception:
        logger.debug("degradation.cache_write_failed", exc_info=True)


def get_cached_answer(question: str) -> dict | None:
    try:
        return _answer_cache().get(_normalized_question_key(question))
    except Exception:
        return None


def keyword_only_retrieve(
    rag: RAGService, question: str, top_k: int, filters: dict
) -> list[RetrievedChunk]:
    """Bypasses Qdrant entirely: BM25 over Postgres DocumentChunk rows only. This is the
    'BM25-only retrieval if dense search times out' tier called for in Phase 1."""
    from app.services.rag import is_relevant_chunk, rerank_chunks

    settings = get_settings()
    candidate_limit = max(20, top_k * 4)
    text_filters = {**(filters or {}), "payload_type": "text"}
    keyword_chunks = rag.keyword_search(question, candidate_limit, text_filters)
    reranked = rerank_chunks(question, keyword_chunks)
    relevant = [
        chunk
        for chunk in reranked
        if is_relevant_chunk(question, chunk, settings.retrieval_min_relevance_score * 0.7)
    ]
    return relevant[:top_k] or reranked[:top_k]


STATIC_DEGRADED_MESSAGE = (
    "We're experiencing high load on our knowledge base right now and can't retrieve "
    "sourced information for this question. Please try again in a few minutes. "
    "If this is urgent, contact your dentist directly."
)
