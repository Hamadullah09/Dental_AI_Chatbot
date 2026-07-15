from __future__ import annotations

import time
from typing import Any

from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CrossEncoderReranker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        if not self.settings.enable_bge_reranker:
            return None
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.settings.bge_reranker_model)
            return self._model
        except Exception as exc:
            logger.warning(f"Failed to load cross-encoder reranker: {exc}")
            return None

    def rerank(self, query: str, chunks: list[dict[str, Any]], top_k: int = 8) -> list[dict[str, Any]]:
        if not chunks:
            return []

        model = self._get_model()
        if model is None:
            return self._lexical_rerank(query, chunks, top_k)

        start = time.perf_counter()
        pairs = [(query, chunk.get("text", "")[:self.settings.bge_reranker_max_chars]) for chunk in chunks]
        scores = model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk["cross_encoder_score"] = float(score)

        reranked = sorted(chunks, key=lambda c: c.get("cross_encoder_score", 0), reverse=True)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"Cross-encoder reranked {len(chunks)} chunks in {duration_ms:.1f}ms")

        return reranked[:top_k]

    def _lexical_rerank(self, query: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        query_words = set(query.lower().split())

        for chunk in chunks:
            text = chunk.get("text", "").lower()
            text_words = set(text.split())
            overlap = len(query_words & text_words)
            lexical_score = overlap / max(len(query_words), 1)
            chunk["cross_encoder_score"] = lexical_score * 0.5 + chunk.get("rerank_score", 0) * 0.5

        reranked = sorted(chunks, key=lambda c: c.get("cross_encoder_score", 0), reverse=True)
        return reranked[:top_k]


cross_encoder_reranker = CrossEncoderReranker()
