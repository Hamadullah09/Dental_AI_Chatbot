from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EvaluationPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()

    def evaluate(self, question: str, answer: str, sources: list[dict], context: str, visuals: list[dict] | None = None) -> dict[str, Any]:
        start = time.perf_counter()

        results = {
            "faithfulness": self._check_faithfulness(answer, context),
            "groundedness": self._check_groundedness(answer, context),
            "citation_accuracy": self._check_citation_accuracy(answer, sources, context),
            "visual_accuracy": self._check_visual_accuracy(answer, visuals or []),
            "hallucination_rate": self._check_hallucination(answer, context),
            "relevance": self._check_relevance(question, answer),
        }

        results["overall_score"] = sum(results.values()) / len(results)
        results["latency_ms"] = (time.perf_counter() - start) * 1000

        return results

    def _check_faithfulness(self, answer: str, context: str) -> float:
        if not context:
            return 0.5
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())
        overlap = len(answer_words & context_words)
        total = len(answer_words) if answer_words else 1
        return min(1.0, overlap / total)

    def _check_groundedness(self, answer: str, context: str) -> float:
        if not context:
            return 0.5
        sentences = [s.strip() for s in answer.split(".") if s.strip()]
        grounded_count = 0
        for sentence in sentences:
            sentence_words = set(sentence.lower().split())
            context_words = set(context.lower().split())
            if len(sentence_words & context_words) >= len(sentence_words) * 0.3:
                grounded_count += 1
        return grounded_count / max(len(sentences), 1)

    def _check_citation_accuracy(self, answer: str, sources: list[dict], context: str) -> float:
        import re
        citations = re.findall(r'\[Source \d+\]', answer)
        if not citations:
            return 1.0 if not sources else 0.5
        return min(1.0, len(sources) / max(len(citations), 1))

    def _check_visual_accuracy(self, answer: str, visuals: list[dict]) -> float:
        if not visuals:
            return 1.0
        visual_references = sum(1 for v in visuals if v.get("document_name", "").lower() in answer.lower())
        return min(1.0, visual_references / max(len(visuals), 1))

    def _check_hallucination(self, answer: str, context: str) -> float:
        if not context:
            return 0.5
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())
        novel_words = answer_words - context_words
        novel_words = {w for w in novel_words if len(w) > 4}
        return 1.0 - min(1.0, len(novel_words) / max(len(answer_words), 1))

    def _check_relevance(self, question: str, answer: str) -> float:
        q_words = set(question.lower().split())
        a_words = set(answer.lower().split())
        overlap = len(q_words & a_words)
        return min(1.0, overlap / max(len(q_words), 1))

    def compute_ranking_metrics(self, ranked_items: list[dict], relevant_ids: list[str], k: int = 10) -> dict[str, float]:
        metrics = {}

        hits = sum(1 for i, item in enumerate(ranked_items[:k]) if item.get("id") in relevant_ids)
        metrics["precision@k"] = hits / k if k > 0 else 0.0
        metrics["recall@k"] = hits / len(relevant_ids) if relevant_ids else 0.0

        mrr = 0.0
        for i, item in enumerate(ranked_items):
            if item.get("id") in relevant_ids:
                mrr = 1.0 / (i + 1)
                break
        metrics["mrr"] = mrr

        dcg = 0.0
        for i, item in enumerate(ranked_items[:k]):
            if item.get("id") in relevant_ids:
                dcg += 1.0 / (i + 1).bit_length()
        ideal_dcg = sum(1.0 / (i + 1).bit_length() for i in range(min(len(relevant_ids), k)))
        metrics["ndcg@k"] = dcg / ideal_dcg if ideal_dcg > 0 else 0.0

        return metrics


evaluation_pipeline = EvaluationPipeline()
