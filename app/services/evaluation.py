import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.rag import RAGService


@dataclass
class EvaluationCase:
    question: str
    expected_terms: list[str]
    expected_sources: list[str]
    filters: dict[str, Any] | None = None


@dataclass
class EvaluationResult:
    question: str
    answer: str
    passed: bool
    term_recall: float
    has_citation: bool
    source_match: bool
    missing_terms: list[str]
    sources: list[str]


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.strip().startswith("#"):
            continue
        payload = json.loads(line)
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValueError(f"Evaluation case on line {line_number} is missing question.")
        cases.append(
            EvaluationCase(
                question=question,
                expected_terms=[str(term).lower() for term in payload.get("expected_terms", [])],
                expected_sources=[str(source).lower() for source in payload.get("expected_sources", [])],
                filters=payload.get("filters"),
            )
        )
    return cases


def evaluate_cases(service: RAGService, cases: list[EvaluationCase], top_k: int = 5) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        answer, citations = service.answer(case.question, top_k=top_k, filters=case.filters)
        answer_l = answer.lower()
        missing_terms = [term for term in case.expected_terms if term not in answer_l]
        term_recall = 1.0 if not case.expected_terms else (len(case.expected_terms) - len(missing_terms)) / len(case.expected_terms)
        source_names = [citation.document_name for citation in citations]
        source_names_l = [name.lower() for name in source_names]
        source_match = not case.expected_sources or any(
            expected in source_name
            for expected in case.expected_sources
            for source_name in source_names_l
        )
        has_citation = any(citation.page_number is not None for citation in citations)
        passed = term_recall >= 0.8 and has_citation and source_match
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
            )
        )
    return results


def summarize_results(results: list[EvaluationResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    average_recall = sum(result.term_recall for result in results) / total if total else 0.0
    citation_rate = sum(1 for result in results if result.has_citation) / total if total else 0.0
    source_match_rate = sum(1 for result in results if result.source_match) / total if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "average_term_recall": round(average_recall, 3),
        "citation_rate": round(citation_rate, 3),
        "source_match_rate": round(source_match_rate, 3),
    }
