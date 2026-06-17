# RAG Phase 2 Status

## Step 1: RAG MVP

| Item | Status | Notes |
| --- | --- | --- |
| PDF books upload | Done | Admin upload supports PDF files and document records. |
| Clean text | Done | Parser removes common PDF artifacts, repairs broken hyphenated words, and normalizes spacing. |
| Chunking | Done | Page-aware chunks retain page number and chunk index. |
| Metadata | Done | Upload captures title, source, year, edition, type, trust, specialty, language, review status, and file hash. |
| Embeddings | Done | Chunks are embedded using the configured embedding service. |
| Qdrant | Done | Chunks are stored as Qdrant points with citation and filter payloads. |
| Answer with citations | Done | Chat answers return document name, page number, chunk index, and score. |

## Step 2: RAG Quality Improve

| Item | Status | Notes |
| --- | --- | --- |
| Hybrid search | Done | Retrieval combines vector search with keyword scoring for exact dental terms. |
| Reranking | Done | Merged candidates are reranked using vector score, keyword score, lexical overlap, trust level, and review status. |
| Metadata filtering | Done | Chat retrieval supports approved/trusted/type/year filters with role-aware defaults. |
| Context compression | Done | Retrieved chunks are shortened to question-relevant sentences before answer generation. |
| Evaluation | Done | `scripts/evaluate_rag.py` scores expected terms, citation presence, and source match using `docs/evaluation_dataset.jsonl`. |

## Remaining Work

- Expand `docs/evaluation_dataset.jsonl` with 50 to 100 expert-reviewed dental questions.
- Add human review labels for answer faithfulness, safety, and citation correctness.
- Add OCR for scanned PDFs with no extractable text.
- Add background job progress events for long PDF ingestion.
- Replace lightweight SQLite schema updates with Alembic migrations for production.
