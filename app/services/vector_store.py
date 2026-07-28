from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.resilience import is_transient_qdrant_error, qdrant_breaker, retry_with_backoff

logger = get_logger(__name__)

# Qdrant operations we proxy are all idempotent from the caller's point of view: reads are
# naturally safe to retry, upserts key by point ID (overwrite), and deletes are filter-based.
# That's what makes blanket retry-on-transient-error safe here rather than call-site-specific.
_NON_RETRIED_METHODS = frozenset()


class ResilientQdrantClient:
    """Transparent proxy around QdrantClient that applies a circuit breaker + bounded
    retry-with-backoff to every method call, so the ~15 call sites across the app get
    fault tolerance for free instead of needing per-call-site wrapping (Phase 1)."""

    def __init__(self, client: QdrantClient, max_attempts: int) -> None:
        self._client = client
        self._max_attempts = max_attempts

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if not callable(attr) or name in _NON_RETRIED_METHODS:
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            def _call() -> Any:
                return attr(*args, **kwargs)

            def _with_retry() -> Any:
                return retry_with_backoff(
                    _call,
                    max_attempts=self._max_attempts,
                    should_retry=is_transient_qdrant_error,
                    name=f"qdrant.{name}",
                )

            from app.services.observability import observability

            with observability.trace_operation(f"qdrant.{name}", {"db.system": "qdrant"}):
                return qdrant_breaker.call(_with_retry)

        return wrapped


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    if settings.qdrant_local_path:
        raw_client = QdrantClient(path=settings.qdrant_local_path)
    elif not settings.qdrant_url:
        raw_client = QdrantClient(path="qdrant_storage")
    else:
        raw_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.qdrant_timeout_seconds,
            check_compatibility=False,
        )
    return ResilientQdrantClient(raw_client, max_attempts=settings.qdrant_max_retry_attempts)  # type: ignore[return-value]


def collection_exists(qdrant: QdrantClient, collection_name: str) -> bool:
    if hasattr(qdrant, "collection_exists"):
        try:
            return bool(qdrant.collection_exists(collection_name=collection_name))
        except Exception:
            pass
    try:
        qdrant.get_collection(collection_name=collection_name)
        return True
    except Exception:
        return False


def ensure_qdrant_collection(
    qdrant: QdrantClient,
    collection_name: str,
    vector_size: int,
    *,
    replace_if_wrong_size: bool = False,
) -> None:
    exists = collection_exists(qdrant, collection_name)
    if exists:
        if not replace_if_wrong_size:
            return
        try:
            info = qdrant.get_collection(collection_name=collection_name)
            vectors = info.config.params.vectors
            current_size = int(getattr(vectors, "size", 0) or 0)
            if current_size == int(vector_size):
                return
        except Exception:
            pass
        qdrant.recreate_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )
        return

    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )
