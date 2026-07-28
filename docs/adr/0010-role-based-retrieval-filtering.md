# ADR-0010: Role-based retrieval trust-level and document-type filtering

Date: 2026-07-28
Status: Accepted

## Context

`docs/GAP_AUDIT_PHASE0.md` finding #2 confirmed `default_trust_levels()` was dead code in
the sense that mattered: both the "patient" and "dentist/student" branches returned the
identical list, so despite `docs/ARCHITECTURE.md`'s existing claim that retrieval was
role-aware, trust-level filtering never actually differed by role in practice. This
matters specifically because the product serves three distinct personas (patient,
dentist, student) with different needs for how conservative retrieved content should be -
a patient asking about a symptom should get only fully-vetted guidance, while a dentist
or student researching the same topic reasonably wants access to a broader evidence base
including research articles.

## Decision

`default_trust_levels()` (`app/services/rag.py`) now actually differs: patients get
`["high"]` only; dentists/students also get `["medium"]`. This pairs with
`default_document_types()` (already role-differentiated before this pass, e.g.
`research_article` excluded for patients) so both trust-level and document-type filtering
agree in spirit. `rerank_chunks()` gained a `user_role` parameter and a
`_ROLE_DOCUMENT_TYPE_BOOST` table so reranking, not just the hard Qdrant filter, also
weights role-appropriate content higher - threaded through all 9 existing call sites
(`RAGService.retrieve()`, `expand_adjacent_chunks()`, and others) rather than added as a
new, ninth, inconsistent call path.

## Consequences

- This is a product/policy decision, not a pure bug fix - "which trust levels each role
  sees by default" is a clinical-content-governance choice, flagged explicitly in the
  code comment on `default_trust_levels()` for a product owner to confirm rather than
  something this pass should have finalized unilaterally. The choice made (patients:
  high-trust only; others: high+medium) is the conservative default in the absence of
  that confirmation.
- Patient-facing answers now draw from a narrower, more vetted document set than before
  this fix - this could reduce answer coverage for niche patient questions that were
  previously (incorrectly) drawing on medium-trust or research-article content. Worth
  watching via `docs/evaluation_dataset.jsonl`'s retrieval quality gate (Phase 5/6) for a
  coverage regression, not just a quality improvement.
- `contains_prescribing_language()` was also made role-aware as part of this same effort
  (patients get stricter prescribing-language screening than dentist/student roles, who
  are expected to discuss medications more directly) - same category of decision, same
  caveat about needing product-owner confirmation of exactly where that line sits.

## Alternatives considered

- **Leave trust-level filtering role-agnostic (both branches identical) but fix
  document-type filtering only**, treating the trust-level parity as intentional.
  Rejected - re-reading the original code and `docs/ARCHITECTURE.md`'s claims together,
  the identical-branches structure reads as an incomplete implementation (a copy-paste
  placeholder), not a deliberate "trust level doesn't vary by role" design choice; leaving
  it broken risked shipping a compliance-relevant gap (patients seeing content intended
  to be gated to professional users) as if it were tested and correct.
- **Make the role-based trust/document-type split configurable per-deployment instead of
  hardcoded.** Deferred as unnecessary complexity until a second deployment actually needs
  a different split - flagged as a reasonable future ask, not built preemptively.
