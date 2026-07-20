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


from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EvaluationCase:
    question: str
    expected_terms: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    filters: dict[str, Any] | None = None
    case_type: str = "general"
    expect_visual: bool = False
    expected_visual_id: str | None = None
    expected_document_id: str | None = None
    expected_page_number: int | None = None
    expected_chunk_index: int | None = None


@dataclass
class EvaluationResult:
    question: str
    answer: str
    passed: bool
    term_recall: float = 0.0
    has_citation: bool = False
    source_match: bool = False
    top5_relevance: bool = False
    citation_accuracy: bool = False
    visual_relevance: bool = False
    answer_faithfulness: bool = False
    missing_terms: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    visuals: list[str] = field(default_factory=list)
    case_type: str = "general"


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    if not path.exists():
        return cases
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            cases.append(
                EvaluationCase(
                    question=data.get("question", ""),
                    expected_terms=data.get("expected_terms", []),
                    expected_sources=data.get("expected_sources", []),
                    filters=data.get("filters"),
                    case_type=data.get("case_type", "general"),
                    expect_visual=data.get("expect_visual", False),
                    expected_visual_id=data.get("expected_visual_id"),
                    expected_document_id=data.get("expected_document_id"),
                    expected_page_number=data.get("expected_page_number"),
                    expected_chunk_index=data.get("expected_chunk_index"),
                )
            )
    return cases


def evaluate_cases(service, cases: list[EvaluationCase], top_k: int = 5) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        try:
            answer, sources = service.answer(case.question, top_k=top_k, filters=case.filters)
        except Exception:
            answer = ""
            sources = []

        answer_lower = answer.lower()
        retrieved_text = answer_lower

        missing_terms = [term for term in case.expected_terms if term not in retrieved_text]
        term_recall = 1.0 if not case.expected_terms else (len(case.expected_terms) - len(missing_terms)) / len(case.expected_terms)

        source_names = [getattr(s, "document_name", str(s)) for s in sources]
        source_names_l = [name.lower() for name in source_names]
        source_match = not case.expected_sources or any(
            expected in source_name
            for expected in case.expected_sources
            for source_name in source_names_l
        )

        has_citation = bool(sources)

        passed = term_recall >= 0.8 and source_match

        results.append(
            EvaluationResult(
                question=case.question,
                answer=answer,
                passed=passed,
                term_recall=term_recall,
                has_citation=has_citation,
                source_match=source_match,
                missing_terms=missing_terms,
                sources=source_names,
                case_type=case.case_type,
            )
        )
    return results


def summarize_results(results: list[EvaluationResult]) -> dict[str, Any]:
    if not results:
        return {"total": 0, "passed": 0, "pass_rate": 0.0}

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_term_recall = sum(r.term_recall for r in results) / total
    citation_rate = sum(1 for r in results if r.has_citation) / total

    return {
        "total": total,
        "passed": passed,
        "pass_rate": passed / total,
        "avg_term_recall": avg_term_recall,
        "citation_rate": citation_rate,
    }
