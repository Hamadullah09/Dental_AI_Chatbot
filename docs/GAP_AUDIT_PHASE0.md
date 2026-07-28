# Phase 0 Gap Audit — Verified Against `main` (cd92e1ae), 2026-07-28

Scope: re-verification of the 9 pre-existing audit findings plus a walk of the components the
original audit did not cover (streaming path, memory, cross-encoder, citation verifier,
Qdrant collection lifecycle, RBAC on clinical routers, CI, dead code). Every claim below was
checked against the working tree at commit `cd92e1ae` ("feat: production-grade chatbot").

Legend: **CONFIRMED** = holds exactly as originally written · **REVISED** = real, but details
changed · **RESOLVED** = no longer true / never was true.

---

## Part 1 — Original findings, re-verified

### 1. LangGraph silent fallback — CONFIRMED (and worse than reported)
`app/routers/chat.py:169` still wraps the entire graph invocation in a bare `except Exception:`
that silently re-runs `RAGService.answer()` — no log, no metric, no trace of the fact that the
safety/citation/confidence nodes didn't run.

Additional detail not in the original finding: the *non-exception* fallback at
`chat.py:162-167` (graph returns something that isn't `AgentState`/dict) calls
`rag.answer(question, top_k=payload.top_k, filters={})` — **with empty filters**. That branch
drops the user's role, trust levels, document scoping, and conversation history entirely.

**Fix (Phase 1):** log with trace ID, emit `agent_graph_fallback_total{reason=...}`, alert on
rate; make the empty-filters branch pass the real filter dict; add the missing regression test.

### 2. Role-aware trust filtering is dead code — CONFIRMED verbatim
`app/services/rag.py:1989-1992`:

```python
def default_trust_levels(user_role: str | None) -> list[str]:
    if user_role == "patient":
        return ["high", "medium"]
    return ["high", "medium"]
```

Both branches identical. `default_document_types()` (rag.py:1995) does differentiate.
**Fix (Phase 5a):** implement intended behavior (patient → `["high"]` default; others opt into
`medium`) + regression test. *Policy decision to confirm with product owner: exact per-role
trust defaults.*

### 3. Role model doesn't match docs — CONFIRMED
`app/models.py:15-19` = `admin/dentist/student/patient`. `docs/ARCHITECTURE.md:72,151` and
`docs/DATABASE.md:27` still document `admin/dentist/hygienist/patient`. `student` is normalized
to `dental_student` only inside `rag.py:1545`.
Nuance: `app/schemas.py:21` says public registration "supports patient, student, and dentist
roles," but `auth.py:63-67` correctly rejects dentist self-registration (403, requires admin
verification) — the schema description is misleading, the code is right.
**Fix (Phase 7 docs + small Phase 2 item):** reconcile docs; decide hygienist's fate; fix the
schema field description.

### 4. `RAG_MODE=agentic` is not agentic — CONFIRMED
`rag.py:195-196`: `elif effective_mode == "agentic": logger.info("rag.agentic.deferred_to_corrective")`.
No tool-calling loop exists. **Fix:** implement or stop claiming it (decision for product owner).

### 5. Safety/self-check are heuristic — CONFIRMED, plus: self-check is OFF by default
`app/agent/nodes/safety.py` is entirely regex (emergency/unsafe-advice/injection/drug-misuse
patterns, English-only). `enable_self_check` defaults to **False** (`config.py:57`) and is not
set in `.env`, so the pattern-based self-check isn't even running. No results are persisted for
evaluation. **Fix (Phase 2/5):** as originally scoped; also decide whether to enable the
existing heuristic as a stopgap.

### 6. Clinical-data scope growth — CONFIRMED, with one upgrade
`appointments.py`, `prescriptions.py`, `dental_records.py`, `dentists.py` are all registered in
`main.py:56-60`. **Better than reported:** server-side RBAC genuinely exists on these routers
(extensive `current_user.role` checks and `require_admin` deps throughout — e.g.
`dental_records.py:233-397`, `prescriptions.py:247-444`). The Phase 2 gap is therefore
encryption-at-rest, field-level audit logging, consent/retention — not basic access control.

### 7. Undocumented scraper subsystem — CONFIRMED
`app/scrapers/`, `app/services/scraper/`, `app/services/dataset_generation.py`, and a tracked
`Database Q&A.csv` (git-tracked, 513 KB) exist; zero mentions of any of them in
`docs/ARCHITECTURE.md`. Licensing/provenance/destination questions from the original finding
remain open (Phase 5b).

### 8. Stale docs — CONFIRMED
`docs/Remaining_Work.md:7,9` still claims Alembic, rate limiting, and structured logging are
missing; all exist (`alembic/versions/`, `RateLimiter` in `chat.py:25`, structlog config).

### 9. Test coverage gaps — CONFIRMED
No test file references `build_langgraph`, any `app/agent` node, `default_trust_levels`, or
`stream_chat_response`. Existing suites: rag quality, llm, auth/chat, ingestion, admin docs,
health, scraper.

---

## Part 2 — New findings from the extended walk

### 10. The streaming path bypasses the LangGraph entirely — the biggest single gap
`app/core/streaming.py:14-186` hand-rolls its own pipeline for `/chat/stream`: safety → memory
→ intent → plain `rag.retrieve()` → generate. On this path there is **no citation verification,
no visual retrieval (`'visuals': []` hardcoded at line 167), no reranking, no multi-query/
corrective/HyDE modes, no self-check**, and `top_k` is clamped to ≤5 (line 86) regardless of
the request. Since the frontend uses streaming (commit `6f29a25e` "add true token streaming"),
the diagram's Citation Verification Agent effectively **never runs on the primary UX path**.
Also: the `metadata` SSE event emits `answer_mode: 'rag_grounded'` at line 126 *before*
generation; if the LLM fails and the general-fallback text is streamed (line 136), the saved
message is still recorded as `rag_grounded`.
**Fix (Phase 1, high priority):** unify — either make the graph streamable (LangGraph supports
`.astream()`) or extract shared node sequence so both paths run the same safety/citation/
memory logic. This is a precondition for constraint #4 (patient-visible output must be
citation-verified).

### 11. Three disjoint "memory" implementations; the graph has none
- `app/agent/nodes/memory.py` (140 lines): **never imported anywhere** — not registered in
  `build_langgraph()` (graph.py:428-443). Dead code.
- `app/services/memory.py` `MemoryService`: used only by the streaming path
  (`streaming.py:70`) and the settings router.
- `rag.py:222-253` `build_memory_context()` (term-overlap heuristic over last 6 turns):
  runs only inside `RAGService.answer()` — i.e., only on the *fallback* path.

Net: the non-streaming graph path — the one with the most nodes — has **no memory at all**,
and each path remembers different things. The roadmap's "memory used only when the current
question shares terms with previous turns" heuristic is confirmed at rag.py:246-248
(term-intersection OR `is_followup_question`).
**Fix (Phase 1/5a):** pick one memory implementation, wire it as a real graph node, delete the
other two or make them adapters.

### 12. Citation "verification" is a 40% word-overlap check that silently edits answers
`app/agent/nodes/citation_verifier.py:66-77`: a sentence is "supported" if ≥40% of its >3-char
words appear anywhere in the concatenated context. Unsupported sentences are **silently deleted
from the answer** (line 40) — which can break markdown/lists and remove `[Source N]` markers —
unless ≤3 sentences would remain, in which case everything is kept regardless. It is invoked
via `planner.py:428-432` wrapped in `except Exception: pass`. Additionally,
`validate_citations` (planner.py:416-426) *backfills* the top-3 retrieved chunks as "sources"
when the answer cited none — fabricating an appearance of citation.
**Fix (Phase 2/5):** replace with a real verifier (embedding-based NLI or LLM check), stop
silent sentence deletion (flag + downgrade `answer_mode` instead), never backfill uncited
sources, persist verdicts for the Phase 3 eval dashboard.

### 13. Cross-Encoder Re-ranking: dead module + disabled flag
`app/services/cross_encoder.py` exports singleton `cross_encoder_reranker` — **imported
nowhere**. `rag.py:2061+` has a *second, separate* inline BGE implementation gated on
`enable_bge_reranker`, which defaults False (`config.py:59`) and is `false` in `.env`. The
graph's `rerank_results` (graph.py:188-215) is just a weighted-sum sort of scores already
computed. So the diagram's "Cross Encoder Re-ranking" box is **not running in any deployed
configuration**. **Fix (Phase 5):** delete one implementation, benchmark, decide default-on
(GPU cost tradeoff), regression-test that it's in the request path.

### 14. "Two Qdrant collections" is wrong — it's one collection with `payload_type`
Text and visuals are both upserted into `settings.qdrant_collection`
(`ingestion.py:219`, `visuals.py:119`) discriminated by `payload_type: text|visual`
(rag.py:80-89, 543). `qdrant_visual_collection = "dental_visuals"` (config.py:39) is **dead
config — referenced nowhere else**. Upside discovered: `delete_document_vectors`
(ingestion.py:160) filters only on `document_id`, so document deletion removes text *and*
visual points together — the "stale visual vectors on delete" concern from the audit prompt is
**RESOLVED** for the delete path. Docs/diagram need correcting; dead setting should be removed.

### 15. Committed default secrets in `.env.docker`
`.env.docker` is git-tracked and contains a default `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and
`ADMIN_PASSWORD`. If any deployment launched from it unmodified, its JWT signing key is public
in the repo history. Local (untracked) `dental_ai.db` — 91 MB SQLite with real-looking data —
sits in the working dir; also `uploaded_docs/`, `backups/`, root-level `draft_dental_qa.jsonl`.
**Fix (Phase 2, first PR):** rotate all three, replace tracked values with placeholders,
document secrets-manager plan, verify none of the local data files are PHI-bearing before any
repo publishing.

### 16. CI security jobs can never fail
Beyond the known `mypy || true` (`ci-cd.yml:53`): `safety check -r requirements.txt || true`
and `bandit ... || true` (lines 82-83). Lint is the only gate with teeth. **Fix (Phase 6):**
baseline-and-enforce for all three.

### 17. Dead/unwired modules inventory
- `app/agent/nodes/memory.py` — never imported (see #11)
- `app/services/cross_encoder.py` — never imported (see #13)
- `app/services/evaluation.py` `evaluation_pipeline` singleton — never imported
- `app/services/observability.py` `ObservabilityManager` — never imported outside its module
  (Phase 3 should build on or replace it deliberately, not accidentally add a third system)
- `graph.py:443` registers `handle_error` node with **no edges routing to it**
- `arq` is in requirements.txt but `app/workers/` is not wired into any process/entrypoint
- role instruction injection in both prompt builders is wrapped in `except Exception: pass`
  (graph.py:396-401, streaming.py:226-230) — a role-shaping failure would be invisible

### 18. `answer_mode` integrity on the streaming path
Covered in #10 but called out separately because it corrupts metrics: `CHAT_QUERIES` and the
stored message's mode can claim `rag_grounded` for answers that actually came from the general
fallback. Any Phase 3 dashboard built before this fix would report wrong grounding rates.

---

## Part 3 — What this changes about the phase plan

1. **"Harden the graph" is the wrong first move — first make the graph the only path.**
   Findings #1, #10, #11 mean there are *three* divergent answer pipelines (graph, streaming,
   RAGService fallback). Phase 1 should start by unifying them; otherwise every safety/quality
   improvement lands on a path users may not hit.
2. **Citation verification needs a rebuild, not hardening** (#12) — constraint #4 ("never relax
   the citation verifier") currently protects a word-overlap heuristic that silently rewrites
   answers and fabricates source lists.
3. **RBAC is in better shape than the audit assumed** (#6) — Phase 2 effort shifts to
   encryption-at-rest, audit logging, secrets (#15), and consent/retention.
4. **Quick wins before any big PR:** fix #1's empty-filters branch, remove dead modules (#17),
   rotate #15's secrets, un-`|| true` the CI security jobs (#16), correct the docs (#3, #8, #14).

## Open policy questions for the product owner (blocking specific items only)
- Per-role trust-level defaults for retrieval (#2 fix shape).
- Keep claiming "agentic RAG" and build it, or rename the mode (#4)?
- Is `hygienist` a planned role or a docs error (#3)?
- Prescriptions: may the AI discuss/confirm dosages at all, or unconditionally route to a human
  dentist (Phase 5b)?
- Scraped content: licensing/attribution status and whether it may feed the live collections
  (#7 / Phase 5b).
