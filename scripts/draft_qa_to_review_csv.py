import argparse
import csv
import json
from pathlib import Path


FIELDS = [
    "instruction",
    "input",
    "output",
    "category",
    "source_document",
    "source_page",
    "source_chunk_id",
    "correctness",
    "safety",
    "language_quality",
    "approved_or_rejected",
    "reviewer_notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert draft dental Q&A JSONL to expert review CSV.")
    parser.add_argument("--input", default="draft_dental_qa.jsonl")
    parser.add_argument("--output", default="draft_dental_qa_review.csv")
    args = parser.parse_args()

    with Path(args.input).open("r", encoding="utf-8") as source, Path(args.output).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            writer.writerow({field: row.get(field, "") for field in FIELDS})
    print(f"Wrote review CSV to {args.output}")


if __name__ == "__main__":
    main()
