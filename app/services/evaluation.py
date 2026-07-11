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
    case_type: str = "text"
    expect_visual: bool = False
    expected_document_id: str | None = None
    expected_chunk_id: str | None = None
    expected_chunk_index: int | None = None
    expected_visual_id: str | None = None
    expected_page_number: int | None = None
    filters: dict[str, Any] | None = None


@dataclass
class EvaluationResult:
    question: str
    answer: str
    passed: bool
    term_recall: float
    has_citation: bool
    source_match: bool
    top5_relevance: bool
    citation_accuracy: bool
    visual_relevance: bool
    answer_faithfulness: bool
    missing_terms: list[str]
    sources: list[str]
    visuals: list[str]
    case_type: str = "text"


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
                case_type=str(payload.get("case_type") or "text"),
                expect_visual=bool(payload.get("expect_visual", False)),
                expected_document_id=payload.get("expected_document_id"),
                expected_chunk_id=payload.get("expected_chunk_id"),
                expected_chunk_index=payload.get("expected_chunk_index"),
                expected_visual_id=payload.get("expected_visual_id"),
                expected_page_number=payload.get("expected_page_number"),
                filters=payload.get("filters"),
            )
        )
    return cases


def evaluate_cases(service: RAGService, cases: list[EvaluationCase], top_k: int = 5) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        rag_result = service.answer(case.question, top_k=top_k, filters=case.filters)
        if isinstance(rag_result, tuple):
            answer, citations = rag_result
            visuals = []
        else:
            answer = rag_result.answer
            citations = rag_result.sources
            visuals = rag_result.visuals or []
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
        top5_relevance = (
            case.expected_chunk_index is None
            or any(citation.chunk_index == case.expected_chunk_index for citation in citations[:5])
        )
        citation_accuracy = (
            not case.expected_document_id
            or any(str(citation.document_id) == str(case.expected_document_id) for citation in citations)
        ) and (
            case.expected_page_number is None
            or any(citation.page_number == case.expected_page_number for citation in citations)
        )
        visual_ids = [visual.visual_id for visual in visuals]
        visual_relevance = (
            any(str(visual.visual_id) == str(case.expected_visual_id) for visual in visuals)
            if case.expect_visual and case.expected_visual_id
            else (bool(visuals) if case.expect_visual else not bool(visuals))
        )
        answer_faithfulness = term_recall >= 0.6 and not any(
            phrase in answer_l
            for phrase in [
                "as an ai",
                "i cannot access",
                "according to unknown",
                "source:",
            ]
        )
        passed = term_recall >= 0.8 and has_citation and source_match and citation_accuracy and visual_relevance and answer_faithfulness
        results.append(
            EvaluationResult(
                question=case.question,
                answer=answer,
                passed=passed,
                term_recall=term_recall,
                has_citation=has_citation,
                source_match=source_match,
                top5_relevance=top5_relevance,
                citation_accuracy=citation_accuracy,
                visual_relevance=visual_relevance,
                answer_faithfulness=answer_faithfulness,
                missing_terms=missing_terms,
                sources=source_names,
                visuals=visual_ids,
                case_type=case.case_type,
            )
        )
    return results


def summarize_results(results: list[EvaluationResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    average_recall = sum(result.term_recall for result in results) / total if total else 0.0
    citation_rate = sum(1 for result in results if result.has_citation) / total if total else 0.0
    source_match_rate = sum(1 for result in results if result.source_match) / total if total else 0.0
    citation_accuracy = sum(1 for result in results if result.citation_accuracy) / total if total else 0.0
    visual_relevance = sum(1 for result in results if result.visual_relevance) / total if total else 0.0
    answer_faithfulness = sum(1 for result in results if result.answer_faithfulness) / total if total else 0.0
    top5_relevance = sum(1 for result in results if result.top5_relevance) / total if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "average_term_recall": round(average_recall, 3),
        "citation_rate": round(citation_rate, 3),
        "source_match_rate": round(source_match_rate, 3),
        "citation_accuracy": round(citation_accuracy, 3),
        "visual_relevance": round(visual_relevance, 3),
        "answer_faithfulness": round(answer_faithfulness, 3),
        "top5_relevance": round(top5_relevance, 3),
        "by_case_type": summarize_by_case_type(results),
    }


def summarize_by_case_type(results: list[EvaluationResult]) -> dict[str, Any]:
    grouped: dict[str, list[EvaluationResult]] = {}
    for result in results:
        grouped.setdefault(result.case_type, []).append(result)
    summary: dict[str, Any] = {}
    for case_type, items in grouped.items():
        total = len(items)
        summary[case_type] = {
            "total": total,
            "pass_rate": round(sum(1 for item in items if item.passed) / total, 3) if total else 0.0,
            "citation_accuracy": round(sum(1 for item in items if item.citation_accuracy) / total, 3) if total else 0.0,
            "visual_relevance": round(sum(1 for item in items if item.visual_relevance) / total, 3) if total else 0.0,
            "faithfulness": round(sum(1 for item in items if item.answer_faithfulness) / total, 3) if total else 0.0,
        }
    return summary
