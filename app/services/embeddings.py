import hashlib
from functools import lru_cache
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.resilience import embedding_breaker, is_transient_network_error, retry_with_backoff


class HashingEmbeddingModel:
    """Small deterministic fallback when transformer embeddings are unavailable."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimensions

    def encode(self, texts: list[str] | str):
        input_texts = [texts] if isinstance(texts, str) else texts
        vectors = [self._embed(text) for text in input_texts]
        return np.array(vectors, dtype=np.float32)

    def _embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        tokens = [token.strip(".,;:!?()[]{}\"'").lower() for token in text.split()]
        for token in tokens:
            if not token:
                continue
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()


def _is_transient_local_inference_error(exc: Exception) -> bool:
    # Embedding inference is local (in-process), not a network call, so the network-error
    # predicate doesn't apply here. Transient failure under load looks like resource
    # exhaustion (GPU OOM, torch/allocator errors), not connection errors.
    return isinstance(exc, (RuntimeError, MemoryError, OSError)) and not is_transient_network_error(exc)


class ResilientEmbeddingModel:
    """Wraps encode() with a circuit breaker + short retry budget, so a transient resource
    spike (e.g. concurrent-load GPU OOM) doesn't take down every retrieval call, while a
    persistently broken model fails fast instead of retrying forever (Phase 1). Also
    caches single-text encodes in Redis (Phase 4) - repeated/common questions are a
    realistic pattern for a patient-education chatbot, and unlike caching a full RAG
    answer, an embedding vector for identical text has no role/session dependency at all,
    so it's always safe to reuse regardless of who asks or what filters apply."""

    def __init__(self, model: Any, model_name: str = "default") -> None:
        self._model = model
        self._model_name = model_name

    def encode(self, *args: Any, **kwargs: Any) -> Any:
        cached = self._try_cache_lookup(*args, **kwargs)
        if cached is not None:
            return cached

        def _call() -> Any:
            return self._model.encode(*args, **kwargs)

        def _with_retry() -> Any:
            return retry_with_backoff(
                _call,
                max_attempts=2,
                base_delay=0.1,
                max_delay=0.5,
                should_retry=_is_transient_local_inference_error,
                name="embedding.encode",
            )

        result = embedding_breaker.call(_with_retry)
        self._try_cache_store(result, *args, **kwargs)
        return result

    def _single_text(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
        texts = args[0] if args else kwargs.get("texts") or kwargs.get("sentences")
        if isinstance(texts, str):
            return texts
        if isinstance(texts, list) and len(texts) == 1 and isinstance(texts[0], str):
            return texts[0]
        return None

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(f"{self._model_name}:{text}".encode()).hexdigest()
        return digest

    def _try_cache_lookup(self, *args: Any, **kwargs: Any) -> Any | None:
        text = self._single_text(args, kwargs)
        if text is None:
            return None
        try:
            from app.core.redis import RedisCache
            cache = RedisCache(prefix="embedding_cache")
            cached = cache.get(self._cache_key(text))
            if cached is None:
                return None
            was_list = bool(args and isinstance(args[0], list)) or "texts" in kwargs or "sentences" in kwargs
            vector = np.array(cached, dtype=np.float32)
            return np.array([vector]) if was_list else vector
        except Exception:
            return None

    def _try_cache_store(self, result: Any, *args: Any, **kwargs: Any) -> None:
        text = self._single_text(args, kwargs)
        if text is None:
            return
        try:
            from app.core.redis import RedisCache
            settings = get_settings()
            cache = RedisCache(prefix="embedding_cache", ttl=settings.embedding_cache_ttl_seconds)
            vector = np.asarray(result)
            flat = vector[0] if vector.ndim == 2 else vector
            cache.set(self._cache_key(text), flat.tolist())
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)


@lru_cache(maxsize=1)
def get_embedding_model():
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer

        return ResilientEmbeddingModel(SentenceTransformer(settings.embedding_model_name), model_name=settings.embedding_model_name)
    except Exception:
        return ResilientEmbeddingModel(HashingEmbeddingModel(), model_name="hashing-fallback")
