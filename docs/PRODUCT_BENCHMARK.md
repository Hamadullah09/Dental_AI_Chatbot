# Product Benchmark — 2026-07-28

A live, hands-on audit of the Dental AI Chatbot: what actually works today (tested through
a real browser, not just read from code), what breaks and why, and what a complete
product still needs. Complements `docs/GAP_AUDIT_PHASE0.md` (a code-level architecture
audit) with something that only running the product end-to-end can surface.

> **Update, 2026-07-29:** the four "Now" tier items below (findings #1-#4 and the
> regex-only safety scope question) have since been fixed - see
> [docs/adr/0015](adr/0015-safety-scope-disclosure-over-unvalidated-classifier.md) and
> [docs/adr/0016](adr/0016-human-review-workflow-for-unreviewed-conversations.md) for the
> safety-scope and expert-review decisions specifically. The findings are left below
> exactly as originally written (this is a dated audit, not a living document), with
> `[FIXED]` markers added inline.

## Test conditions

Run fully locally, without Docker (Docker Desktop's engine wasn't reachable in this
environment) and with Ollama deliberately unreachable, matching the situation this audit
was requested in:

- Backend: `uvicorn` directly, SQLite (`dental_ai_local.db`, fresh), Redis genuinely
  available, Qdrant in embedded/local mode pointed at this machine's existing
  `qdrant_storage/` directory (two real collections already on disk from earlier work —
  `dental_docs` at 54,301 points and `dental_docs_clean` at 43,129 points, ~608MB total).
- Ollama: `OLLAMA_BASE_URL` pointed at a port nothing listens on, so every LLM call fails
  with a real connection refusal — the actual scenario this audit was asked to check.
- Frontend: `next dev`, pointed at the local backend.
- Browser: the in-app Browser pane (the Claude in Chrome extension wasn't connected this
  session — the extension needs installing/signing in for that path).

One environment quirk worth naming so it isn't mistaken for a product bug: this machine's
Docker Desktop backend process was still holding port 8000 from an earlier session even
though the Docker engine itself wasn't reachable, which caused non-deterministic-looking
request failures (IPv4 curl calls and IPv6 browser calls were silently hitting two
different processes) until traced down. The backend was moved to port 8001 to sidestep
it. Anyone re-running this: check `netstat -ano | findstr :8000` before assuming a
result is a real bug.

## Confirmed working

| Area | What was tested | Result |
|---|---|---|
| Auth | Register (patient), register (student path available), login, JWT issuance, logout, account menu | Works |
| Auth | Dentist self-registration | Correctly **blocked** server-side with a clear message — see Findings |
| Chat | Send message, session history, sidebar search/pin, new chat, theme toggle | Works |
| Chat | Message actions: edit, copy, like/dislike, retry | Present and wired |
| Chat | Streaming (`/chat/stream`) behavior when Ollama is unreachable | Degrades **well** — see Findings |
| Chat | Voice-to-text | Real browser Web Speech API (`webkitSpeechRecognition`), no backend dependency |
| Chat | Web search toggle | Real Tavily/Brave integration in `app/services/web_search.py`; needs an API key configured to actually return results (none set in this test's `.env`) |
| Appointments | Booking form (dentist select, date/time, duration, reason, notes), list view | Form is complete; list empty-state is clean. Dentist dropdown was empty because no dentists exist in this fresh local DB — not a bug, no seed data |
| Prescriptions | List view | Clean empty state |
| Dental Records | List view | Clean empty state |
| Dentists directory | Search/filter by specialization, list view | Works once the local port-8000 conflict (above) was resolved |
| Settings | Theme, push/email notification toggles, language (English/Urdu/Arabic), timezone, chat history retention control, data-sharing consent, HIPAA consent acknowledgment, download-my-data, delete-account | All present and render correctly — see Findings for what's cosmetic vs. enforced |
| Admin — Clinical library | Document upload form (title, author, year, edition, type, trust level, specialty, language, review status), PDF list, "Generate Draft Q&A Dataset" | Complete, and has real prior-use evidence in this environment (25 chunks / 125 Q&A rows already generated from an orthodontics textbook) |
| Admin — Analytics dashboard | `/admin/dashboard`: total queries, retrieval/LLM latency, citation accuracy, hallucination rate, failed retrievals, answer-mode breakdown | Live and real — "Total Queries: 2" matched this session's actual test count exactly, not a stub |
| Security | CORS, security response headers, rate limiting | Verified directly via response headers; correctly configured |
| Resilience | Circuit breaker opens after 3 consecutive Ollama failures, `/api/health` reports granular per-dependency status | Confirmed via live logs — Phase 1/3 behavior works as designed |

## Findings from this test session

Ranked by how much they'd affect a real user or operator.

### 1. The dentist user role is a complete dead end `[FIXED 2026-07-29]`
Registration now creates a real, immediately-usable patient account plus a pending
verification request (license number required); `GET/POST /admin/dentist-requests/...`
lets an admin actually list, approve, or reject one. See
[ADR](adr/0010-role-based-retrieval-filtering.md)-adjacent work in
`app/routers/auth.py` and `app/routers/admin.py`, plus `frontend/app/admin/dentist-requests/page.tsx`.

The registration UI advertises "Dentist access request (admin verification required)."
Submitting it is correctly rejected server-side (`app/routers/auth.py`) with that exact
message. But **no endpoint anywhere** — not in `app/routers/admin.py`, not anywhere else
— lets an admin actually grant or verify a dentist account. The role exists throughout
the retrieval/reranking logic (`default_trust_levels()`, `default_document_types()`,
role-based prompt shaping — see [ADR-0010](adr/0010-role-based-retrieval-filtering.md))
but there is currently no way for a real dentist to ever obtain one. This is a product
gap, not a bug in the code that exists — the missing piece is an admin-facing
"verify/create dentist account" workflow.

### 2. `/api/chat` and `/chat/stream` handle an Ollama outage inconsistently `[FIXED 2026-07-29]`
Root cause: `generate_direct_answer()` (`app/agent/nodes/planner.py`, the "what is X"
direct-answer shortcut only the non-streaming graph path takes) had a bare
`except Exception: state.answer = settings.medical_disclaimer` that never reset
`answer_mode`, leaving it at its stale `"rag_grounded"` default. Now reports
`answer_mode: "service_unavailable"` with the same honest message the streaming path
already used, which `app/routers/chat.py` turns into a real 503. See
`tests/test_agent_graph.py`'s three new regression tests.

With Ollama unreachable:
- **Streaming** (`app/core/streaming.py`) shows the user: *"Dental AI service is
  temporarily unavailable. Please try again shortly. For pain, swelling, fever,
  bleeding, infection, medication, diagnosis, or treatment decisions, consult a licensed
  dentist."* — clear, honest, safety-conscious. Good.
- **Non-streaming** `/api/chat` (`app/routers/chat.py`) returns **HTTP 200** with
  `{"answer": "<just the disclaimer text>", "answer_mode": "rag_grounded", "sources": []}`
  — a hollow, contentless answer mislabeled as a successful grounded response. A
  consumer of this endpoint (e.g., a future mobile client, or any integration built
  against it) would have no signal that generation actually failed.

Given the non-negotiable rule that any patient-facing output must be traceable and
honest about its own failure modes, the non-streaming path should be brought in line
with the streaming path's behavior, not the other way around.

### 3. First-touch latency after Ollama fails is much worse than the circuit breaker's own goal
The Ollama call itself fails fast (~5 seconds, 2 retries, as designed —
[ADR-0002](adr/0002-circuit-breakers-and-degradation-tiers.md)). But the *rest* of the
pipeline isn't bounded the same way:
- The sentence-transformer embedding model is loaded **lazily on first use** in a fresh
  process, not pre-warmed at startup. In this test, that alone took ~30 seconds (would be
  much longer on a machine without the model already cached from Hugging Face, e.g. a
  freshly deployed container).
- Local/embedded Qdrant mode is, by Qdrant's own runtime warning, "not recommended" at
  this data's actual scale (43K–54K points) — retrieval against it is measurably slow.
- Total: a single chat request took **~80–90 seconds** end-to-end before the user saw
  any response, even though the "Ollama is down" fact was known within 5 seconds of the
  request starting.

None of this is wrong per se — the fixes (pre-warm the embedding model at app startup,
move off embedded-mode Qdrant at this data volume — already flagged as a real tradeoff in
[k8s/README.md](../k8s/README.md)) are already partially documented — but it hadn't been
observed end-to-end under an actual Ollama outage before this test, and the total
latency is a real UX problem independent of Ollama.

### 4. Chat History Retention is a setting with no enforcement behind it `[FIXED 2026-07-29]`
The setting is now persisted (`UserSettings.chat_history_retention_days`, previously
missing from the schema entirely — the frontend was sending several fields, including
this one, that the backend silently dropped every save: `push_notifications`,
`data_sharing_consent`, `hipaa_consent` too, all fixed together) and enforced by a real
daily `arq` cron job, `enforce_chat_retention_task` (`app/workers/tasks.py`), deleting
each user's chat sessions past their own chosen window.

The Settings page lets a user pick 30 days / 90 days / 6 months / 1 year for "Chat
History Retention." There is no matching code anywhere in the backend (`grep -rn
retention app/` returns nothing) — no scheduled job, no deletion logic. This is worth
fixing soon specifically because it's privacy-adjacent: a user who picks "30 days"
believing their history is actually purged on that schedule is being told something
false by the UI.

### 5. A client-side OpenAI fallback was started but never finished
`frontend/.env.local` has `NEXT_PUBLIC_OPENAI_BACKUP_TIMEOUT_MS` and
`BACKUP_OPENAI_TIMEOUT_MS`, and `frontend/app/api/openai-fallback/` exists as a route
directory — but it contains zero files. This looks like exactly the right idea for
resilience (the backend already has a real `OPENAI_API_KEY` configured in `.env`, and
`LLM_PROVIDER` could plausibly support this as a documented failover path) but it was
scaffolded and abandoned. Worth either finishing it (as a real, evaluated resilience
addition — see the non-negotiable constraint on not swapping core model providers
without an explicit evaluation) or removing the dead scaffolding so it doesn't look
finished to the next person who finds it.

### 6. Help Center has no content `[PARTIALLY ADDRESSED 2026-07-29]`
Not a code gap — the page and its data model work — it just has zero articles authored.
One real article now exists (seeded at startup, idempotent): "How Dental AI's safety
checks work (and their limits)" — see finding #3 in the "Now" list below, which this
also closes. Fixing it also surfaced and fixed a real, separate bug: `HelpArticleRead`
couldn't parse the stored comma-joined `tags` column at all — any tagged article, seeded
or admin-created, 500'd on every `GET`. General content authoring beyond this one
article is still open.

## Built at the API level, unreachable from the product

- `GET /admin/feedback` (the feedback review queue added this hardening pass, Phase 5) —
  no frontend page calls it. An admin cannot currently see submitted feedback anywhere in
  the UI, only via direct API access. (Still open — the new Expert Review workflow below
  is a separate, distinct thing from this user-feedback queue, not a replacement for it.)

## What a complete dental AI chatbot product should have

Organized as a treatment plan — most clinically/legally load-bearing first.

### Now (safety, trust, and correctness gaps)
1. **`[DONE]` Fix the two findings above that touch user trust directly**: the `/api/chat`
   hollow-answer inconsistency (#2) and the non-enforced retention setting (#4) — both
   are cases where the product currently tells the user something that isn't true.
2. **`[DONE]` A real path to a dentist account** (#1) — without this, the entire
   dentist/student/patient role-differentiated retrieval and prompt system
   ([ADR-0010](adr/0010-role-based-retrieval-filtering.md)) has no real dentist user to
   serve.
3. **`[DONE, as explicit disclosure]` Verified safety/self-check beyond regex.**
   `docs/GAP_AUDIT_PHASE0.md` finding #5 and `docs/Remaining_Work.md` both already flag
   this: emergency-triage and prescribing-language detection are pattern-based, not a
   verified clinical system. Decided explicitly (see
   [ADR-0015](adr/0015-safety-scope-disclosure-over-unvalidated-classifier.md)) not to
   build a classifier in this pass — an unvalidated one would be dishonest to call
   "verified" — and instead made the real scope and limits an actual, user-reachable Help
   Center article linked from the persistent chat disclaimer. A genuinely validated
   classifier remains real future work, not solved by this.
4. **`[DONE]` A human expert review workflow for unreviewed conversations**, distinct
   from the existing user-submitted feedback queue — a domain expert sampling real
   conversations against a rubric (faithfulness, safety, citation correctness) and
   recording labels over time. See [ADR-0016](adr/0016-human-review-workflow-for-unreviewed-conversations.md),
   `GET /admin/reviews/sample`, `POST /admin/reviews/{message_id}`,
   `GET /admin/reviews/summary`, and `frontend/app/admin/expert-reviews/page.tsx`. This
   is a workflow, not an automated grader — it produces value only if someone
   domain-qualified actually uses it regularly; nothing here invents a review cadence.

### Next (product completeness)
5. **Notification delivery.** Settings has toggles for push and email notifications;
   there's no evidence of an actual notification-sending system (no push provider
   integration found, no transactional email service). Appointment reminders and
   prescription-related alerts are a natural, expected feature for a dental product with
   an appointments module already built.
6. **Admin feedback review UI** — still open. Not the same thing as the new Expert
   Review workflow (item 4 above, oldest-unreviewed-conversations sampled against a
   fixed rubric) - this is specifically a UI for `GET /admin/feedback`, the
   user-submitted ratings queue, which still has no frontend page calling it.
7. **Expand the retrieval evaluation dataset.** 30 cases
   (`docs/evaluation_dataset.jsonl`) is a start; a product this document-heavy (54K+
   indexed chunks) needs meaningfully more expert-reviewed questions for
   `scripts/ci_retrieval_gate.py` to be a strong quality signal rather than a smoke test.
8. **Pre-warm the embedding model and any other lazily-loaded ML models at app startup**,
   not on the first user request that happens to need them (Finding #3).
9. **A decision on Qdrant at scale** — embedded/local mode already warns it isn't
   recommended past 20K points and this product is at 2–3x that; `k8s/README.md`
   already lays out the managed-vs-self-hosted-cluster tradeoff, it just needs to
   actually be decided and acted on for whichever environment serves real users.

### Later (depth and ecosystem)
10. **Deeper appointment/booking**: calendar sync (Google/Outlook), SMS reminders,
    dentist-side availability management UI (the booking form and data model exist;
    a dentist's own scheduling view does not appear to).
11. **Practice-management/EHR integration** — the single biggest adoption blocker for
    real dental practices is almost always "does this talk to what we already use,"
    not model quality.
12. **Cost and usage tracking** for LLM/API calls (Ollama compute time, any OpenAI/Tavily/
    Brave usage) surfaced next to the existing quality metrics on the analytics
    dashboard, so quality and cost are visible together.
13. **Accessibility and mobile-responsiveness audit** — not checked in this pass; worth
    its own dedicated review given the product's patient-facing surface.
14. **Multi-language answer generation**, not just retrieval-side language filtering —
    Settings already offers Urdu/Arabic as a preference; confirm the LLM prompt actually
    produces answers in the selected language, not just retrieves in it.

## Related documents

- [docs/GAP_AUDIT_PHASE0.md](GAP_AUDIT_PHASE0.md) — the code-level architecture audit that
  preceded the Phase 1-7 hardening pass
- [docs/adr/](adr/) — why each hardened subsystem behaves the way it does
- [docs/RUNBOOK.md](RUNBOOK.md) — what to do when one of these subsystems is actually
  failing in production
- [docs/Remaining_Work.md](Remaining_Work.md) — the code-level "what's left" tracker this
  document complements with live-tested findings
