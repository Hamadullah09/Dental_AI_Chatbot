import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.evaluation import EvaluationResult, evaluate_cases, load_evaluation_cases, summarize_results
from app.services.rag import RAGService, generate_query_variants, rewrite_query_for_retrieval


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Dental AI RAG retrieval and answer quality.")
    parser.add_argument("--dataset", default="docs/evaluation_dataset.jsonl", help="Path to JSONL evaluation cases.")
    parser.add_argument("--top-k", type=int, default=5, help="Final number of chunks sent to answer generation.")
    parser.add_argument("--max-cases", type=int, help="Evaluate only the first N cases for fast tuning.")
    parser.add_argument(
        "--case-type",
        action="append",
        help="Evaluate only matching case_type values. Repeat for multiple types.",
    )
    parser.add_argument("--collection", help="Evaluate against a specific Qdrant collection without editing .env.")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Score retrieved chunks, citations, and visuals without calling the answer-generation LLM.",
    )
    parser.add_argument(
        "--failures-jsonl",
        default="cleanup_reports/retrieval_benchmark_failures.jsonl",
        help="Write failed-case retrieval inspection records to this JSONL path.",
    )
    parser.add_argument(
        "--skip-failure-log",
        action="store_true",
        help="Skip failed-case re-retrieval logging for faster threshold sweeps.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    settings = get_settings()
    if args.collection:
        settings.qdrant_collection = args.collection

    service = RAGService()
    cases = load_evaluation_cases(Path(args.dataset))
    if args.case_type:
        allowed_case_types = set(args.case_type)
        cases = [case for case in cases if case.case_type in allowed_case_types]
    if args.max_cases:
        cases = cases[: max(1, args.max_cases)]
    if args.retrieval_only:
        results = evaluate_retrieval_cases(service, cases, top_k=args.top_k)
    else:
        results = evaluate_cases(service, cases, top_k=args.top_k)
    summary = summarize_results(results)
    failure_path = Path(args.failures_jsonl)
    if not args.skip_failure_log:
        write_failure_log(service, cases, results, failure_path, top_k=args.top_k, retrieval_only=args.retrieval_only)
    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "results": [result.__dict__ for result in results],
                    "failure_log": str(failure_path),
                },
                indent=2,
            )
        )
        return

    print("Dental AI RAG Evaluation")
    print(json.dumps(summary, indent=2))
    if not args.skip_failure_log:
        print(f"Failed-case inspection log: {failure_path}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(safe_console_text(f"{status} | recall={result.term_recall:.2f} | citation={result.has_citation} | {result.question}"))
        if result.missing_terms:
            print(safe_console_text(f"  missing_terms: {', '.join(result.missing_terms)}"))


def safe_console_text(value: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


def write_failure_log(service: RAGService, cases, results, path: Path, top_k: int, retrieval_only: bool = False) -> None:
    failed_records = []
    case_by_question = {case.question: case for case in cases}
    for result in results:
        if result.passed:
            continue
        case = case_by_question.get(result.question)
        filters = case.filters if case else None
        failed_records.append(build_failure_record(service, result, filters=filters, top_k=top_k, retrieval_only=retrieval_only))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in failed_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_failure_record(
    service: RAGService,
    result,
    filters: dict[str, Any] | None,
    top_k: int,
    retrieval_only: bool = False,
) -> dict[str, Any]:
    question = result.question
    rewritten = rewrite_query_for_retrieval(question)
    variants = []
    if service.settings.enable_query_rewriting and not retrieval_only:
        variants = generate_query_variants(question, max_variants=getattr(service.settings, "multi_query_max_variants", 4))
    try:
        chunks = service.retrieve_for_mode(question, top_k=top_k, filters=filters or {})
    except Exception as exc:
        chunks = []
        retrieval_error = str(exc)
    else:
        retrieval_error = None

    if result.case_type in {"visual", "table_chart", "negative_no_visual"}:
        try:
            visuals = service.retrieve_visuals(question, chunks, filters=filters or {})
        except Exception as exc:
            visuals = []
            visual_error = str(exc)
        else:
            visual_error = None
    else:
        visuals = []
        visual_error = None

    return {
        "query": question,
        "case_type": result.case_type,
        "rewritten_query": rewritten,
        "rewritten_queries": variants,
        "top_retrieved_chunks": [chunk_debug_payload(chunk) for chunk in chunks[:10]],
        "selected_visuals": [visual_debug_payload(visual) for visual in visuals[:8]],
        "final_citations": result.sources,
        "answer_preview": result.answer[:800],
        "missing_terms": result.missing_terms,
        "scores": {
            "term_recall": result.term_recall,
            "has_citation": result.has_citation,
            "source_match": result.source_match,
            "top5_relevance": result.top5_relevance,
            "citation_accuracy": result.citation_accuracy,
            "visual_relevance": result.visual_relevance,
            "answer_faithfulness": result.answer_faithfulness,
        },
        "errors": {
            "retrieval": retrieval_error,
            "visual": visual_error,
        },
    }


def evaluate_retrieval_cases(service: RAGService, cases, top_k: int) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        try:
            chunks = service.retrieve_for_mode(case.question, top_k=top_k, filters=case.filters or {})
        except Exception:
            chunks = []
        if case.expect_visual or case.case_type == "negative_no_visual":
            try:
                visuals = service.retrieve_visuals(case.question, chunks, filters=case.filters or {})
            except Exception:
                visuals = []
        else:
            visuals = []

        retrieved_text = " ".join(chunk.text for chunk in chunks).lower()
        missing_terms = [term for term in case.expected_terms if term not in retrieved_text]
        term_recall = 1.0 if not case.expected_terms else (len(case.expected_terms) - len(missing_terms)) / len(case.expected_terms)
        source_names = [chunk.citation.document_name for chunk in chunks]
        source_names_l = [name.lower() for name in source_names]
        source_match = not case.expected_sources or any(
            expected in source_name
            for expected in case.expected_sources
            for source_name in source_names_l
        )
        has_citation = any(chunk.citation.page_number is not None for chunk in chunks)
        top5_relevance = (
            case.expected_chunk_index is None
            or any(chunk.citation.chunk_index == case.expected_chunk_index for chunk in chunks[:5])
        )
        citation_accuracy = (
            not case.expected_document_id
            or any(str(chunk.citation.document_id) == str(case.expected_document_id) for chunk in chunks)
        ) and (
            case.expected_page_number is None
            or any(chunk.citation.page_number == case.expected_page_number for chunk in chunks)
        )
        visual_relevance = (
            any(str(visual.citation.visual_id) == str(case.expected_visual_id) for visual in visuals)
            if case.expect_visual and case.expected_visual_id
            else (bool(visuals) if case.expect_visual else not bool(visuals))
        )
        answer_faithfulness = bool(chunks) and term_recall >= 0.6
        passed = term_recall >= 0.8 and has_citation and source_match and citation_accuracy and visual_relevance
        results.append(
            EvaluationResult(
                question=case.question,
                answer=" ".join(chunk.text for chunk in chunks[:3]),
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
                visuals=[visual.citation.visual_id for visual in visuals],
                case_type=case.case_type,
            )
        )
    return results


def chunk_debug_payload(chunk) -> dict[str, Any]:
    return {
        "document": chunk.citation.document_name,
        "document_id": chunk.citation.document_id,
        "page_number": chunk.citation.page_number,
        "chunk_index": chunk.citation.chunk_index,
        "reranker_score": chunk.rerank_score,
        "vector_score": chunk.vector_score,
        "bm25_score": chunk.keyword_score,
        "query_relevance_score": chunk.metadata.get("query_relevance_score"),
        "section_title": chunk.metadata.get("section_title"),
        "chapter_title": chunk.metadata.get("chapter_title"),
        "quality_score": chunk.metadata.get("quality_score"),
        "text_preview": " ".join(chunk.text.split())[:600],
    }


def visual_debug_payload(visual) -> dict[str, Any]:
    return {
        "visual_id": visual.citation.visual_id,
        "document": visual.citation.document_name,
        "document_id": visual.citation.document_id,
        "page_number": visual.citation.page_number,
        "visual_type": visual.citation.visual_type,
        "score": visual.rerank_score,
        "image_path": visual.citation.image_path,
        "caption_text": visual.citation.caption_text,
        "generated_description": visual.citation.generated_description,
    }


if __name__ == "__main__":
    main()
