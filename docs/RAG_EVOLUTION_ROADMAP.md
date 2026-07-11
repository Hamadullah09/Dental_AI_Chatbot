# Dental AI RAG Evolution Roadmap

This roadmap upgrades Dental AI from Simple RAG to Agentic RAG without breaking the existing chat, upload, citation, and history workflows.

## Configuration

Use these environment flags to move through stages safely:

```env
RAG_MODE=simple
ALLOW_GENERAL_FALLBACK=true
ENABLE_MEMORY=true
ENABLE_HYDE=false
ENABLE_SELF_CHECK=false
RETRIEVAL_MIN_RELEVANCE_SCORE=1.1
MULTI_QUERY_MAX_VARIANTS=4
OLLAMA_TOP_P=0.8
```

Supported `RAG_MODE` values:

- `simple`
- `memory`
- `multi_query`
- `hyde`
- `adaptive`
- `corrective`
- `self_rag`
- `agentic`

`agentic` is reserved for the future tool-orchestration stage. For now it routes through corrective retrieval so the app remains safe and stable.

## Stage 1: Simple RAG Stabilization

Status: implemented.

- PDF chunks carry document name, page number, chunk index, trust metadata, quality score, and noise reasons.
- Noisy questionnaire, table, reference, bibliography, index, and `/H17040` style artifacts are filtered before generation.
- Qdrant retrieval pulls candidates, reranks them, then passes only the best relevant chunks to Qwen3.
- If no relevant evidence is found, the backend either returns insufficient evidence or uses general fallback depending on `ALLOW_GENERAL_FALLBACK`.
- RAG answers are labeled as uploaded-reference based and citations are returned separately by the backend.

## Stage 2: RAG With Memory

Status: first implementation behind `ENABLE_MEMORY`.

- Recent chat turns are passed from the database-backed chat session into RAG.
- Memory is used only when the current question shares terms with previous turns or looks like a follow-up.
- Memory affects retrieval but does not replace uploaded document evidence.
- Older unrelated messages are ignored to avoid retrieval pollution.

Future work:

- Add a persistent long-chat memory summary column or table through a migration.
- Add explicit memory evaluation cases.

## Stage 3: Multi-Query RAG

Status: implemented as deterministic query expansion behind `RAG_MODE=multi_query` or adaptive/corrective modes.

- Generates variants for clinical terminology, patient-friendly wording, and Roman Urdu hints.
- Retrieves for each variant.
- Merges and deduplicates chunks.
- Reranks against the original question before generation.

Future work:

- Add optional Qwen-generated query rewriting with strict JSON output.

## Stage 4: HyDE RAG

Status: implemented behind `ENABLE_HYDE=true` and `RAG_MODE=hyde` or corrective retry.

- Runs only when initial retrieval confidence is low.
- Generates a hypothetical retrieval passage using Qwen3.
- Embeds and retrieves using that hypothetical passage.
- Never shows the HyDE text to users.

## Stage 5: Adaptive RAG

Status: initial router implemented behind `RAG_MODE=adaptive`.

Current query classes:

- `simple_dental_explanation`
- `symptom_guidance`
- `treatment_question`
- `document_specific`
- `roman_urdu`
- `emergency_safety`
- `admin_document_query`
- `out_of_domain`

The router selects simple, memory, multi-query, corrective, or fallback/refusal behavior based on query type.

## Stage 6: Corrective RAG

Status: implemented behind `RAG_MODE=corrective`.

- Validates chunk relevance before generation.
- If retrieval confidence is weak, retries with multi-query retrieval.
- If enabled and still weak, tries HyDE.
- If evidence remains weak, it does not let Qwen3 answer from unrelated context.

## Stage 7: Self-RAG

Status: first safety/grounding check implemented behind `ENABLE_SELF_CHECK=true` or `RAG_MODE=self_rag`.

Checks:

- Answer is at least minimally grounded in retrieved context.
- Answer does not include prescribing language.
- Safety note appears for symptoms, medication, trauma, children, pregnancy, fever, pus, bleeding, or pain questions.
- Roman Urdu requests do not return Urdu/Arabic/Devanagari script.

Future work:

- Store self-check results in a dedicated evaluation table.
- Add Qwen-based verifier with a strict schema.

## Stage 8: Agentic RAG

Status: planned, not fully implemented.

Future tools:

- `search_vector_db`
- `search_keyword_bm25`
- `rerank_chunks`
- `check_chunk_relevance`
- `summarize_context`
- `generate_answer_qwen`
- `safety_checker`
- `citation_checker`
- `memory_reader`
- `document_metadata_filter`
- `fallback_general_answer`
- `ask_clarifying_question`

Agent rules:

- Plan internally, never expose chain-of-thought.
- Retrieve evidence before answering.
- Verify relevance and citations.
- Use fallback only when evidence is weak and fallback is enabled.
- Never diagnose or prescribe.

## Stage 9: Multimodal RAG

Status: future.

Prepare for dental image/X-ray support only after an image model and secure storage/review workflow are available.

## Stage 10: Graph RAG

Status: future.

Potential graph concepts:

- disease
- symptom
- treatment
- drug
- risk factor
- specialty
- guideline

Do not overbuild until the document corpus and evaluation set are stable.
