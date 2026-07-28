# ADR-0001: Unify the three RAG execution paths into one node-function pipeline

Date: 2026-07-28
Status: Accepted

## Context

`docs/GAP_AUDIT_PHASE0.md` findings #1 and #10 established that this product had three
separate, drifting implementations of "answer a question with retrieval": the LangGraph
`build_langgraph()` state machine (`app/agent/graph.py`), a hand-rolled SSE streaming path
(`app/core/streaming.py`) that duplicated retrieval/generation logic rather than calling
the graph, and a synchronous `RAGService.answer()` fallback in `app/routers/chat.py` that
`/api/chat` silently used whenever `build_langgraph()` raised *any* exception - with no
logging, so a broken graph could run in production for weeks as "the fallback" without
anyone noticing (finding #1). The streaming path bypassing the graph entirely (finding
#10) meant a fix to, say, citation verification landed in `/api/chat` but not
`/chat/stream`, or vice versa, without anyone deciding that split was intentional.

## Decision

Extract the graph's retrieval/generation/verification logic into standalone node
functions (`run_safety_check`, `load_memory_context`, `classify_intent`, `rewrite_query`,
`retrieve_chunks`, `retrieve_visuals`, `rerank_results`, `build_context`,
`run_self_check_and_adjust_answer`, `populate_sources_and_visuals`, `validate_citations`)
that both `build_langgraph()`'s compiled graph *and* `app/core/streaming.py` call
directly, instead of `streaming.py` reimplementing the logic inline. The `/api/chat`
silent fallback now logs at error level and increments `AGENT_GRAPH_FALLBACK_TOTAL`
(Phase 3) every time it's hit, so a broken graph is a visible incident, not silent
degradation.

## Consequences

- A change to any node function (e.g. a citation-verification fix) now automatically
  applies to both the synchronous and streaming chat paths - there is exactly one
  implementation of each step, not two.
- The non-negotiable constraint from this hardening pass's brief - "do not change
  LangGraph node contracts without updating every caller" - is now enforceable in
  practice: there are only two callers (the compiled graph and the streaming path), both
  in-repo, both using the same function signatures.
- The `RAGService.answer()` fallback in `chat.py` still exists as a last-resort path (the
  graph can still fail to *compile*, e.g. a LangGraph library issue), but it is no longer
  silent - operators get a metric and a log line, and can decide whether "the fallback is
  currently serving traffic" is acceptable for their situation.

## Alternatives considered

- **Delete the streaming path and make `/chat/stream` proxy through the compiled graph's
  own streaming support.** Rejected for this pass: LangGraph's native streaming emits
  intermediate state deltas shaped around the graph's internal node names, not the
  SSE event contract (`token`, `sources`, `queued`, etc.) the frontend already depends on
  (a versioned external API contract per this pass's brief) - reshaping that would be a
  frontend-affecting change requiring its own evaluation, out of scope here.
- **Leave the two paths separate and just keep them manually in sync via code review.**
  Rejected - this is exactly the discipline that had already failed once (that's how the
  drift in finding #10 happened) and has no mechanism forcing it going forward.
