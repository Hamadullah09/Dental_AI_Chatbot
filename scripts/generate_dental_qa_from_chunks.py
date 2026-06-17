import argparse
import json
import time
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from app.core.config import get_settings  # noqa: E402


CATEGORIES = [
    "patient_friendly",
    "student_explanation",
    "short_answer",
    "roman_urdu",
    "safety_refusal",
    "emergency_referral",
    "insufficient_evidence",
]


def read_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def processed_chunk_ids(output_path: Path) -> set[str]:
    processed: set[str] = set()
    for row in read_jsonl(output_path) or []:
        chunk_id = row.get("source_chunk_id")
        if chunk_id:
            processed.add(str(chunk_id))
    return processed


def build_prompt(chunk: dict[str, Any], examples_per_chunk: int) -> str:
    categories = ", ".join(CATEGORIES)
    return f"""
Create {examples_per_chunk} draft dental Q&A examples from the provided evidence chunk.

Rules:
- Use only the evidence in the chunk.
- Do not invent facts.
- Do not diagnose or prescribe.
- If the chunk has insufficient evidence, create an insufficient_evidence example.
- Include patient-safe wording and citations in the answer text when helpful.
- Return strict JSON only with key "items" containing an array.
- Each item must include: instruction, input, output, category.
- category must be one of: {categories}

Source document: {chunk.get("document_name")}
Source page: {chunk.get("page_number")}
Chunk text:
{chunk.get("text", "")[:3500]}
""".strip()


def generate_items(client: OpenAI, model: str, chunk: dict[str, Any], examples_per_chunk: int) -> list[dict[str, Any]]:
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You generate expert-review draft dental Q&A from evidence chunks. Return valid JSON only.",
            },
            {"role": "user", "content": build_prompt(chunk, examples_per_chunk)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draft dental Q&A JSONL from clean chunks.")
    parser.add_argument("--input", default="chunks.jsonl")
    parser.add_argument("--output", default="draft_dental_qa.jsonl")
    parser.add_argument("--skipped", default="skipped_chunks.jsonl")
    parser.add_argument("--examples-per-chunk", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    settings = get_settings()
    api_key = settings.openai_api_key
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required in environment or .env.")

    model = args.model or settings.openai_model
    client = OpenAI(api_key=api_key)
    output_path = Path(args.output)
    skipped_path = Path(args.skipped)
    already_processed = processed_chunk_ids(output_path)

    count = 0
    with output_path.open("a", encoding="utf-8") as output, skipped_path.open("a", encoding="utf-8") as skipped:
        for chunk in read_jsonl(Path(args.input)) or []:
            chunk_id = str(chunk.get("chunk_id") or "")
            if not chunk_id or chunk_id in already_processed:
                continue
            if args.limit and count >= args.limit:
                break
            try:
                items = generate_items(client, model, chunk, args.examples_per_chunk)
                valid_count = 0
                for item in items:
                    category = item.get("category")
                    if category not in CATEGORIES:
                        category = "student_explanation"
                    row = {
                        "instruction": str(item.get("instruction") or "").strip(),
                        "input": str(item.get("input") or "").strip(),
                        "output": str(item.get("output") or "").strip(),
                        "category": category,
                        "source_document": chunk.get("document_name"),
                        "source_page": chunk.get("page_number"),
                        "source_chunk_id": chunk_id,
                        "review_status": "pending_review",
                    }
                    if row["instruction"] and row["output"]:
                        output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        valid_count += 1
                if valid_count == 0:
                    skipped.write(json.dumps({"chunk_id": chunk_id, "reason": "no_valid_items"}, ensure_ascii=False) + "\n")
                count += 1
                if args.sleep:
                    time.sleep(args.sleep)
            except Exception as exc:
                skipped.write(json.dumps({"chunk_id": chunk_id, "reason": str(exc)}, ensure_ascii=False) + "\n")
    print(f"Processed {count} chunks. Output: {args.output}. Skipped: {args.skipped}.")


if __name__ == "__main__":
    main()
