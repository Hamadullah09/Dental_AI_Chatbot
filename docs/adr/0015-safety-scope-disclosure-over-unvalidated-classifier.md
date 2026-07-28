# ADR-0015: Explicit safety-scope disclosure instead of an unvalidated "classifier"

Date: 2026-07-29
Status: Accepted

## Context

`docs/PRODUCT_BENCHMARK.md` (the live-tested feature audit) asked for one of two things:
"verified safety/self-check beyond regex... or an explicit, communicated scope limit -
not an implicit one." `docs/GAP_AUDIT_PHASE0.md` finding #5 and
[ADR-0011](0011-emergency-triage-short-circuit.md) already established that emergency
triage, prescribing-language detection, and self-check grounding
(`app/agent/nodes/safety.py`, `app/services/rag.py`'s `self_check_answer()`) are
pattern-based - regex and keyword matching - not a trained or clinically validated
model. That fact was previously only documented in code comments and ADRs: genuinely
invisible to the people who most need to know it - patients relying on the product, and
whoever is accountable for it clinically or legally.

## Decision

Do not build a "classifier" in this pass. A hastily-trained model with no real
validation data, no clinical review, and no ongoing evaluation process would not
actually be a "verified" safety system - it would be an unvalidated one wearing a more
convincing label, which is a worse outcome than the current honest, narrow, pattern-based
system: it invites exactly the false confidence explicit disclosure is meant to prevent.

Instead: make the existing system's real scope a genuine, user-reachable disclosure.
`app/services/users.py`'s `seed_safety_scope_help_article()` seeds a Help Center article
(idempotent, checked by title, safe to run on every startup - same pattern as
`seed_admin_user()`) stating plainly what the checks do (a fixed red-flag phrase list for
emergency triage, prescribing-language redirection, per-sentence groundedness checking)
and do not do (no clinical validation, will miss unfamiliar phrasing, not a diagnostic
system). `frontend/components/ChatInput.tsx`'s persistent disclaimer footer - shown on
every chat turn - now links to it directly ("How our safety checks work"), so the
disclosure sits next to the moment it's most relevant, not buried in a Help Center a user
would have to think to visit.

## Consequences

- No new false confidence is introduced: the product does not claim clinical validation
  it doesn't have, in either code or user-facing copy.
- This is a product/policy call, not a pure engineering one - flagging it here rather
  than deciding silently, per this project's standing instruction to surface exactly this
  category of decision. If the product later invests in a real, clinically validated
  safety classifier, this ADR and the seeded article should be revisited together - the
  disclosure's honesty depends on staying in sync with what's actually true underneath.
- The underlying pattern-based checks are unchanged and remain exactly as capable (and
  exactly as limited) as before this pass - this ADR closes the *disclosure* gap, not the
  *capability* gap. `docs/PRODUCT_BENCHMARK.md`'s roadmap still lists a validated
  classifier and a human expert review workflow ([ADR-0016](0016-human-review-workflow-for-unreviewed-conversations.md))
  as real future work, not as solved.
- Building the article's seed surfaced a real, separate pre-existing bug in
  `HelpArticleRead` (`app/schemas.py`): the schema declared `tags: list[str]` but the
  underlying `HelpCenterArticle.tags` column is a single comma-joined string
  (`app/routers/settings.py` writes it that way) - handing that raw string to a bare
  `list[str]` Pydantic field raised a validation error on every read, meaning `GET
  /help/articles` would 500 for any article that had tags at all, seeded or
  admin-created. Fixed with a `mode="before"` validator that splits the stored string
  back into a list - unrelated to the disclosure decision itself, but directly blocking
  it, so fixed in the same change rather than worked around.

## Alternatives considered

- **Build a lightweight embedding-similarity or small fine-tuned classifier for red-flag
  detection.** Rejected for this pass - genuinely validating a clinical safety
  classifier (labeled data review, sensitivity/specificity testing against real
  presentations, an accountable clinical reviewer) is a substantial project of its own,
  not something to fit inside a single hardening pass alongside three other product
  fixes. Attempting a shortcut version and calling it "verified" would be dishonest.
- **Say nothing and leave the limitation undocumented outside code comments.** This was
  the status quo the finding called out directly - rejected as the one option that
  doesn't actually close the gap.
- **Put the disclosure only in `docs/COMPLIANCE.md` (an internal/operator-facing
  document).** Rejected as insufficient on its own - the people most affected by not
  knowing this system's limits are patients, who don't read internal compliance docs;
  the Help Center article plus an in-product link is what actually reaches them.
