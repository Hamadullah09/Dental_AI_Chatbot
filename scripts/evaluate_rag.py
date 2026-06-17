import argparse
import json
from pathlib import Path

from app.services.evaluation import evaluate_cases, load_evaluation_cases, summarize_results
from app.services.rag import RAGService


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Dental AI RAG retrieval and answer quality.")
    parser.add_argument("--dataset", default="docs/evaluation_dataset.jsonl", help="Path to JSONL evaluation cases.")
    parser.add_argument("--top-k", type=int, default=5, help="Final number of chunks sent to answer generation.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    cases = load_evaluation_cases(Path(args.dataset))
    results = evaluate_cases(RAGService(), cases, top_k=args.top_k)
    summary = summarize_results(results)
    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "results": [result.__dict__ for result in results],
                },
                indent=2,
            )
        )
        return

    print("Dental AI RAG Evaluation")
    print(json.dumps(summary, indent=2))
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} | recall={result.term_recall:.2f} | citation={result.has_citation} | {result.question}")
        if result.missing_terms:
            print(f"  missing_terms: {', '.join(result.missing_terms)}")


if __name__ == "__main__":
    main()
