# Remaining Work

This document previously claimed Alembic migrations, rate limiting, and structured
logging were still missing - all three already existed in the codebase when that was
written (`alembic/`, `slowapi` in requirements.txt, `structlog`/`python-json-logger`). That
mismatch is exactly why this file should be verified against the actual code before being
trusted, rather than treated as ground truth - see `docs/GAP_AUDIT_PHASE0.md` finding #8.
Rewritten below to reflect what's actually done (as of the production-hardening pass
covering Phases 0-6 in `docs/GAP_AUDIT_PHASE0.md`) vs. genuinely still open.

## Done in this pass (previously listed here as "remaining")

- Alembic migrations, API rate limiting (per-user + per-IP), structured JSON logging,
  request IDs, admin audit logs - all pre-existing, now verified and (for rate limiting)
  extended to endpoints that had none (upload).
- PDF ingestion moved off the request-serving process: the arq-based async worker
  (`app/workers/tasks.py`) existed but was never wired up; it's now the primary path with
  in-process fallback (Phase 4).
- PHI controls: field-level encryption at rest for `Prescription`/`DentalRecord` sensitive
  columns, audit logging on PHI access, and `docs/COMPLIANCE.md` documenting what's still
  missing (BAAs, data residency, right-to-erasure, consent, retention) rather than
  claiming this is fully solved (Phase 2).
- Admin feedback review: `GET /admin/feedback` (Phase 5) - previously feedback could be
  submitted but never reviewed.
- Citation verification exists (`app/agent/nodes/citation_verifier.py`) but is a
  word-overlap heuristic, not a real verifier - see the "RAG Quality" gaps below, this is
  not resolved, just more precisely characterized now. Phase 6 added an integration test
  (`tests/test_rag_pipeline_integration.py`) against a real (embedded) Qdrant collection
  covering the grounded-answer and trimmed-hallucination cases, and documented (rather
  than silently left) a real edge case: short answers (<=3 sentences after trimming) are
  flagged internally but not edited - see that test file and `docs/RUNBOOK.md`'s citation
  pass rate drop scenario.
- Safety classifiers for emergency scenarios: red-flag patterns now short-circuit to a
  fixed triage message instead of running the full generation pipeline (Phase 5a).
  Medication/pediatric/pregnancy-specific classifiers are still regex heuristics, not a
  verified system - see below.
- CI for linting, tests, and dependency scanning already existed but `mypy`/`safety`/
  `bandit` were all piped through `|| true`, so none of them could actually fail the
  build. Phase 6 fixed this for real: `mypy` now runs a baseline ratchet
  (`scripts/mypy_baseline_gate.py`, `mypy_baseline.txt` - fails only on *new* errors, not
  the ~166 pre-existing ones in untouched legacy modules); `bandit` and `safety` are now
  genuinely blocking, with every finding either fixed or suppressed with a documented,
  time-boxed reason (`pyproject.toml`'s `[tool.bandit]`, `.safety-policy.yml`) - see
  `docs/adr/0013-mypy-baseline-ratchet.md` and `docs/adr/0014-bandit-safety-ci-gates.md`.
- OpenAPI schema drift: `docs/openapi.json` is now a committed, CI-checked snapshot
  (`scripts/check_openapi_sync.py`) instead of undocumented/unchecked (Phase 7).
- Blue-green/canary deployment and Ollama model-version-swap strategy: documented in
  `docs/DEPLOYMENT.md` for both the docker-compose and Kubernetes paths (Phase 6) - not
  automated, and the real-canary (Argo Rollouts/service mesh) option is explicitly
  flagged as a new infra dependency needing its own evaluation, not built.
- Architecture decisions from Phases 1-6 are now recorded in `docs/adr/` and an
  operational runbook exists (`docs/RUNBOOK.md`) covering Ollama-down, Qdrant-degraded,
  latency-spike, and citation-pass-rate-drop scenarios (Phase 7).

## Still genuinely open

- **Public admin registration**: `ALLOW_ADMIN_REGISTRATION` exists as an escape hatch but
  is not automatically disabled after first bootstrap - if you rely on this flag, confirm
  it's off in any real deployment; nothing in the code enforces that for you.
- **RAG evaluation dataset**: `docs/evaluation_dataset.jsonl` has 30 cases (Phase 5) - more
  expert-reviewed questions would make `scripts/ci_retrieval_gate.py` a stronger signal.
- **Human review labels for faithfulness/safety/citation correctness**: the feedback
  review queue (Phase 5) surfaces user ratings, but there's no structured workflow for a
  domain expert to label a sample of *unreviewed* conversations against a rubric (this is
  different from user-submitted feedback) - Phase 3's task description asked for an
  "evaluation/quality dashboard" tracking this over time, which was not built here; the
  citation/retrieval CI gate is the closest thing that exists.
- **Self-check / safety detection is still heuristic, not verified**: `ENABLE_SELF_CHECK`
  and `app/agent/nodes/safety.py` are pattern-based (grounding-in-context word overlap,
  prescribing-language regex, emergency-keyword regex). No LLM- or embedding-based
  verifier exists yet, and results aren't persisted for evaluation over time.
- **Frontend**: still the original Next.js app: no rework was in scope for this pass.
- **Environment-specific deployment guides**: `k8s/README.md` (Phase 4) and
  `docs/DEPLOYMENT.md` exist for Docker Compose / Kubernetes, but there's no guide for
  e.g. a specific cloud provider's managed services.
- **Backup/restore**: `docs/BACKUP.md` exists; confirm it's still accurate given the
  encryption/backup gap noted in `docs/ARCHITECTURE.md`'s Security Architecture section
  (backups are not confirmed encrypted despite `SecurityManager.encrypt_backup()` existing).
