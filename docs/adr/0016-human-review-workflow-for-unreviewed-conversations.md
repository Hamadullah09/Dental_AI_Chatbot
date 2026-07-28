# ADR-0016: Human expert review workflow for unreviewed conversations

Date: 2026-07-29
Status: Accepted

## Context

`docs/PRODUCT_BENCHMARK.md`'s roadmap named a specific gap: "a human expert review
workflow for unreviewed conversations, distinct from user-submitted feedback... a domain
expert sampling real conversations against a rubric is the only way to track
faithfulness/safety over time." `docs/Remaining_Work.md` had flagged the same thing
earlier, phrased slightly differently: the existing `Feedback` table
(`POST /api/feedback`, surfaced for admins via Phase 5's `GET /admin/feedback`) is a
*patient's own* rating of one answer they happened to react to - it says nothing about
the (likely much larger) set of conversations no one rated at all, and it isn't a
substitute for a domain expert deliberately checking answer quality against a
consistent rubric.

## Decision

Add a second, separate review surface: `ExpertReview` (`app/models.py`), one row per
reviewed assistant message, with three fixed-vocabulary ratings -
`faithfulness` (faithful / partially_faithful / unfaithful), `safety`
(safe / concerning / unsafe), `citation_accuracy` (accurate / partially_accurate /
inaccurate / not_applicable) - plus free-text notes. Three admin endpoints:
`GET /admin/reviews/sample` (oldest-unreviewed-assistant-messages-first, same "systematic
coverage over time" rationale as the dentist-request queue in
[ADR-0010](0010-role-based-retrieval-filtering.md)'s neighbor decisions), `POST
/admin/reviews/{message_id}` (create-or-update a review - a reviewer revising their own
assessment updates the row rather than accumulating a history of them), and `GET
/admin/reviews/summary` (aggregate percentages and counts per rating, meant to sit
alongside `/admin/dashboard`'s automated metrics - those measure what the system reports
about itself, this measures what an independent human reviewer actually found).

`answer_mode` is now also stored in `Message.sources_json` (both the streaming and
non-streaming chat paths - `app/routers/chat.py`) specifically so a reviewer sampling a
conversation can see what mode produced it (`rag_grounded` / `general_fallback` /
`service_unavailable` / ...) without re-running the pipeline - a small, additive,
backward-compatible change (existing rows without the key just read back as `None`,
which every reader already handles with `.get()`).

## Consequences

- There is now a real, queryable signal for "how good are our answers, independent of
  whether a user happened to leave feedback" - previously the only quality signal at all
  was whichever small fraction of users bothered to rate an answer.
- This is a *workflow*, not an automated grader - it produces value only if someone
  domain-qualified actually uses it regularly. Nothing in this pass wires it into a
  cadence (e.g. "review N conversations per week") or an alert if the review queue grows
  unbounded - that's a staffing/process decision for whoever operates the product, not
  something to invent a schedule for here.
- One review per message (`message_id` is unique) is a deliberate v1 simplification -
  if the product later wants multiple independent reviewers' opinions on the same answer
  (useful for measuring reviewer agreement), that's a real schema change (drop the
  uniqueness constraint, add per-reviewer aggregation), not a reinterpretation of the
  current one.
- This complements, and does not replace, [ADR-0015](0015-safety-scope-disclosure-over-unvalidated-classifier.md)'s
  disclosure decision - human review of sampled conversations is exactly the kind of
  ongoing validation that would need to happen before any future automated safety
  classifier could honestly be called "verified."

## Alternatives considered

- **Extend the existing `Feedback` table with an `is_expert_review: bool` flag** instead
  of a separate table. Rejected - conflates two different actors and two different
  purposes (a patient's spontaneous reaction vs. a domain expert's deliberate,
  rubric-driven assessment) in one table, which would make both harder to query
  correctly later (e.g. "average patient satisfaction" would need to remember to
  exclude expert rows, an easy mistake to reintroduce).
- **A free-text-only review** (just notes, no fixed categories). Rejected - fixed
  categories are what make `GET /admin/reviews/summary`'s aggregation ("60% faithful,
  10% unsafe") possible at all; free text alone can't be tracked as a trend over time
  without someone manually reading and re-categorizing every note.
- **Random sampling instead of oldest-unreviewed-first.** Considered - oldest-first was
  chosen for the same reason as the dentist-request queue: it guarantees the review
  backlog actually gets worked down to zero given enough reviewer time, rather than
  random sampling potentially reviewing the same recent slice repeatedly while an old
  conversation sits unreviewed indefinitely. A future iteration could add true random
  sampling as an alternative mode if systematic bias in *which* conversations get
  reviewed (e.g. always the same time-of-day traffic) turns out to matter.
