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
    persistently broken model fails fast instead of retrying forever (Phase 1)."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def encode(self, *args: Any, **kwargs: Any) -> Any:
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

        return embedding_breaker.call(_with_retry)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)


@lru_cache(maxsize=1)
def get_embedding_model():
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer

        return ResilientEmbeddingModel(SentenceTransformer(settings.embedding_model_name))
    except Exception:
        return ResilientEmbeddingModel(HashingEmbeddingModel())
