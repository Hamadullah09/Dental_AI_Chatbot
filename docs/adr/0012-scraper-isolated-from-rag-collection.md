# ADR-0012: Scraper/dataset-generation pipeline kept isolated from the live RAG Qdrant collection

Date: 2026-07-28
Status: Accepted

## Context

Phase 5b's brief asked for scraper/dataset governance and clinical-data-scope review.
`docs/GAP_AUDIT_PHASE0.md` finding #7 confirmed an undocumented scraper subsystem exists
(`app/services/scraper/`) that ingests dentist directory listings, and
`app/services/dataset_generation.py` generates synthetic Q&A training/eval examples from
existing document chunks via an LLM. Before doing any governance work on these, it was
necessary to verify a specific risk: could either pipeline write into the same Qdrant
collection (`dental_docs`, see `docs/ARCHITECTURE.md`'s corrected description in finding
#14) that live chat retrieval queries, which would mean unreviewed scraped or
synthetically-generated content could silently surface as a cited "source" in a patient-
or dentist-facing answer.

## Decision

After tracing both pipelines' write paths, this pass confirmed neither writes to the RAG
collection: the scraper's `DentistEmbeddingService` writes dentist-profile embeddings to
a **separate** Qdrant collection used only by `app/routers/dentists.py`'s directory
search, never joined with `RAGService.retrieve()`'s document-chunk search; and
`dataset_generation.py`'s output is JSONL training/eval examples written to disk
(`docs/evaluation_dataset.jsonl`-style files), never upserted into any Qdrant collection
at all - it reads existing chunks to generate synthetic Q&A pairs, it doesn't feed them
back in. Given this, no additional data-flow governance (e.g. a review-status gate before
scraper output could reach chat answers) was needed for *this specific risk* - the
governance work for Phase 5b instead focused on documenting what each subsystem actually
does and its own data-handling practices (`docs/DATASET_GENERATION_PIPELINE.md` and the
scraper's existing test coverage), not building a safeguard against a risk that doesn't
exist in the current architecture.

## Consequences

- This is a verified-negative, not an unexamined assumption - worth stating plainly
  because "I checked and it's fine" is exactly the kind of claim that should be
  re-verified if either pipeline is ever refactored. If `DentistEmbeddingService` or
  `dataset_generation.py` is ever changed to write into `dental_docs` (e.g. to make
  dentist profiles searchable from the main chat, or to auto-ingest synthetic Q&A as
  training data), that change must re-open this exact question and add the review-status
  gating that `app/services/ingestion.py`'s normal document pipeline already has
  (`review_status` payload field, checked by `build_qdrant_filter()`) - it does not exist
  today because it was never needed for the pipelines as they currently work.
- No code changes resulted from this ADR - it exists specifically so a future maintainer
  doesn't have to re-trace both pipelines from scratch to answer "can scraped/synthetic
  content reach a patient's chat answer," and so the answer ("no, verified, but only
  because of how they're wired today") isn't lost.

## Alternatives considered

- **Add review-status gating to the scraper/dataset-generation output preemptively**,
  even though it's not currently needed. Rejected as unnecessary work for this pass -
  building a safeguard against a risk that doesn't exist in the current data flow is
  exactly the kind of scope creep this hardening pass's brief warned against ("don't add
  features beyond what the task requires"). Documented as a required follow-up
  *if and when* either pipeline's scope changes, instead.
