import hashlib
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


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


@lru_cache(maxsize=1)
def get_embedding_model():
    settings = get_settings()
    try:
        return SentenceTransformer(settings.embedding_model_name)
    except Exception:
        return HashingEmbeddingModel()
