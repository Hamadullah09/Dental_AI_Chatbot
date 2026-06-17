# Dataset Generation Pipeline

This pipeline turns uploaded dental PDFs into a cleaner expert-review dataset for future model experiments. It does not replace RAG. The production chatbot should continue using retrieval for evidence and citations.

## 1. Noisy Chunk Filtering

During PDF ingestion, every chunk is scored by `app/services/chunk_quality.py`.

The detector marks chunks as noisy when they contain patterns such as:

- `/H17040` or related WHO survey glyph artifacts
- tick/cross instructions
- questionnaire or survey wording
- response scales such as Never, Very often, Fairly often, Sometimes, and Don't know
- mostly symbols, numbers, table fragments, or form layouts
- references, index, bibliography, annex, or appendix pages
- repeated headers/footers
- very short text

The metadata stored with every chunk includes:

- `chunk_id`
- `document_id`
- `document_name`
- `page_number`
- `chunk_index`
- `text`
- `quality_score`
- `is_noisy`
- `noise_reasons`
- `review_status`
- `document_type`
- `trust_level`

Normal chat retrieval excludes noisy chunks by default. Questionnaire/form chunks are only allowed when the user specifically asks about surveys, questionnaires, or oral health assessment forms.

## 2. Export Clean Chunks

Export clean chunks from Qdrant:

```bash
python scripts/export_clean_chunks.py --output chunks.jsonl --min-quality 0.60 --limit 100
```

Use `--include-noisy` only for audit/debugging:

```bash
python scripts/export_clean_chunks.py --output all_chunks.jsonl --include-noisy
```

Example output line:

```json
{"chunk_id":"...","document_name":"Dental Caries Textbook","page_number":54,"chunk_index":12,"text":"clean useful text...","quality_score":0.91}
```

## 3. Generate Draft Dental Q&A

Set the OpenAI key in local `.env` only:

```bash
cp .env.example .env
```

Then set:

```text
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o-mini
```

Never commit `.env` or a real API key.

Generate draft examples:

```bash
python scripts/generate_dental_qa_from_chunks.py \
  --input chunks.jsonl \
  --output draft_dental_qa.jsonl \
  --skipped skipped_chunks.jsonl \
  --examples-per-chunk 5 \
  --limit 10
```

The script resumes automatically by skipping chunks already present in the output file. Failed or unsuitable chunks are written to `skipped_chunks.jsonl`.

Draft item schema:

```json
{
  "instruction": "...",
  "input": "...",
  "output": "...",
  "category": "patient_friendly",
  "source_document": "...",
  "source_page": 54,
  "source_chunk_id": "...",
  "review_status": "pending_review"
}
```

Supported categories:

- `patient_friendly`
- `student_explanation`
- `short_answer`
- `roman_urdu`
- `safety_refusal`
- `emergency_referral`
- `insufficient_evidence`

## 4. Expert Review CSV

Convert draft JSONL to a review CSV:

```bash
python scripts/draft_qa_to_review_csv.py \
  --input draft_dental_qa.jsonl \
  --output draft_dental_qa_review.csv
```

Review columns:

- `correctness`
- `safety`
- `language_quality`
- `approved_or_rejected`
- `reviewer_notes`

Only expert-approved rows should be used for fine-tuning experiments.

## 5. Export Approved Dataset

After review, export approved rows:

```bash
python scripts/export_approved_qa.py \
  --input draft_dental_qa_review.csv \
  --output dental_qa.jsonl
```

Output format:

```json
{"instruction":"...","input":"...","output":"..."}
```

## 6. Future Qwen3-14B QLoRA Experiment

Use `dental_qa.jsonl` as the reviewed dataset for a future Qwen3-14B-Instruct QLoRA experiment with LLaMA-Factory.

Recommended flow:

1. Keep RAG as the source of evidence.
2. Fine-tune only for style, structure, safety behavior, Roman Urdu handling, and refusal behavior.
3. Do not fine-tune to memorize textbook knowledge.
4. Serve the fine-tuned adapter through vLLM, Ollama, or another OpenAI-compatible local endpoint.
5. Keep citations and evidence grounding in the existing RAG pipeline.
