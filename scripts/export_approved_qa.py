import argparse
import csv
import json
from pathlib import Path


def is_approved(value: str) -> bool:
    return value.strip().lower() in {"approved", "approve", "yes", "y", "1", "true"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export approved dental Q&A rows to fine-tuning JSONL.")
    parser.add_argument("--input", default="draft_dental_qa_review.csv")
    parser.add_argument("--output", default="dental_qa.jsonl")
    args = parser.parse_args()

    written = 0
    with Path(args.input).open("r", encoding="utf-8", newline="") as source, Path(args.output).open("w", encoding="utf-8") as target:
        reader = csv.DictReader(source)
        for row in reader:
            if not is_approved(row.get("approved_or_rejected", "")):
                continue
            item = {
                "instruction": row.get("instruction", "").strip(),
                "input": row.get("input", "").strip(),
                "output": row.get("output", "").strip(),
            }
            if item["instruction"] and item["output"]:
                target.write(json.dumps(item, ensure_ascii=False) + "\n")
                written += 1
    print(f"Exported {written} approved rows to {args.output}")


if __name__ == "__main__":
    main()
