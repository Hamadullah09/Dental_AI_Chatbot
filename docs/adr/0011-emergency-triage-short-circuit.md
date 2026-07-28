# ADR-0011: Deterministic emergency-triage short-circuit ahead of LLM generation

Date: 2026-07-28
Status: Accepted

## Context

`docs/GAP_AUDIT_PHASE0.md` finding #5 noted safety/self-check logic in this product is
heuristic (regex/keyword-based), not a clinical safety system, and that self-check was
off by default. For genuinely dangerous presentations - facial swelling spreading
rapidly with difficulty breathing (airway compromise risk), uncontrolled bleeding, etc. -
routing the query through the full retrieval-and-LLM-generation pipeline before any
safety response is shown means the *fastest possible path to "seek emergency care now"*
still goes through retrieval latency, Ollama's queue (see ADR-0003), and generation time,
and depends on the LLM reliably producing an appropriately urgent response under prompt
variation.

## Decision

`run_safety_check()` (`app/agent/nodes/safety.py`) now detects a fixed set of red-flag
patterns (regex-matched, e.g. `facial\s+swelling\s+(spreading|rapid)` combined with
breathing difficulty) and, when matched, sets `state.answer_mode = "emergency_triage"`
with a deterministic, pre-written `EMERGENCY_TRIAGE_MESSAGE` - no LLM call, no retrieval.
`_route_after_safety_check()` (`app/agent/graph.py`) routes this case directly to
`format_response`, bypassing `load_memory_context`, `classify_intent`,
`retrieve_chunks`, and `generate_answer` entirely. This is intentionally separate from
(and takes priority over) the existing heuristic safety/self-check logic - it's a small,
fixed, deliberately conservative pattern set for the narrow "this needs emergency care
right now" case, not a replacement for the broader safety system.

## Consequences

- The most time-critical safety response class now has the lowest possible latency and
  zero dependency on LLM behavior/Ollama availability - it works even if Ollama is fully
  down (circuit breaker open, see ADR-0002) or under heavy queue load (see ADR-0003).
- This is necessarily a narrow, high-precision pattern set - it will miss many genuine
  emergencies phrased differently (a known, accepted limitation, not a claim of clinical
  completeness) and is not a substitute for the disclaimer-driven "always recommend
  professional evaluation" language already present in every response. It should never be
  represented to users or stakeholders as clinical triage; it's a deterministic
  fast-path for a specific set of red-flag phrasings, layered on top of - not replacing -
  the existing safety disclaimers.
- Any change to `EMERGENCY_TRIAGE_MESSAGE`'s wording or the regex pattern set is a
  clinical-safety-adjacent product decision, not a routine copy change - per this
  hardening pass's non-negotiable constraint that patient-facing output must remain
  traceable/appropriately cautious, changes here warrant the same scrutiny as citation
  verification changes, not less.

## Alternatives considered

- **Rely on the LLM's own judgment to recognize emergencies and respond urgently**,
  without a deterministic short-circuit. Rejected - this is exactly the "heuristic, not
  guaranteed" gap finding #5 flagged; for the narrow set of unambiguous red-flag
  presentations, a deterministic, zero-latency, zero-dependency path is strictly safer
  than hoping generation produces an appropriately urgent response under load or model
  variation.
- **Route emergencies through the full pipeline but with a high-priority queue slot** for
  the concurrency gate (ADR-0003). Rejected as insufficient on its own - even a
  fast-tracked LLM call is slower and less certain than a pre-written, unconditional
  response, and doesn't help at all if Ollama itself is down.
