from __future__ import annotations

import hashlib
import json

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import RedisCache

logger = get_logger(__name__)

# Generational cache invalidation (Phase 4): rather than trying to enumerate which cached
# queries a specific document affects (impossible to know cheaply without a reverse
# index), every cached retrieval-result key embeds the current "generation" number.
# Bumping the generation on any document delete/re-ingest makes every previously-cached
# entry unreachable in O(1), without needing to delete anything explicitly. The stale
# entries simply expire off their own TTL.
_GENERATION_KEY = "retrieval_cache_generation"


def _generation_cache() -> RedisCache:
    # Long TTL, not "forever" - if this key expires the counter just resets to 0, which
    # is self-healing (see bump_generation's docstring) rather than a correctness issue.
    return RedisCache(prefix="retrieval_cache_meta", ttl=30 * 86400)


def _results_cache() -> RedisCache:
    settings = get_settings()
    return RedisCache(prefix="retrieval_cache", ttl=settings.embedding_cache_ttl_seconds)


def current_generation() -> int:
    try:
        value = _generation_cache().get(_GENERATION_KEY)
        return int(value) if value is not None else 0
    except Exception:
        return 0


def bump_generation() -> None:
    """Call this whenever a document is deleted or re-ingested (app/services/ingestion.py,
    app/routers/admin.py delete_document) so cached retrieval results referencing
    now-stale chunks stop being served."""
    try:
        _generation_cache().set(_GENERATION_KEY, current_generation() + 1)
    except Exception:
        logger.debug("retrieval_cache.bump_generation_failed", exc_info=True)


def _cache_key(question: str, rag_mode: str, top_k: int, filters: dict, generation: int) -> str:
    normalized_question = " ".join(question.strip().lower().split())
    # sort_keys for a stable hash regardless of dict insertion order
    filters_repr = json.dumps(filters or {}, sort_keys=True, default=str)
    raw = f"{generation}:{rag_mode}:{top_k}:{normalized_question}:{filters_repr}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def get_cached_chunks(question: str, rag_mode: str, top_k: int, filters: dict) -> list[dict] | None:
    try:
        key = _cache_key(question, rag_mode, top_k, filters, current_generation())
        return _results_cache().get(key)
    except Exception:
        return None


def cache_chunks(question: str, rag_mode: str, top_k: int, filters: dict, chunks: list[dict]) -> None:
    try:
        key = _cache_key(question, rag_mode, top_k, filters, current_generation())
        _results_cache().set(key, chunks)
    except Exception:
        logger.debug("retrieval_cache.write_failed", exc_info=True)
