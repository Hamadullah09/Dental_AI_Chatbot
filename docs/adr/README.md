# Architecture Decision Records

Phase 7 (Documentation & Handoff). Each ADR is a short, dated record of one decision made
during the Phase 0-6 production-hardening pass: what the situation was, what was decided,
what it costs, and what else was considered. They exist so a future maintainer doesn't
have to reverse-engineer *why* something is the way it is from the diff alone, and so a
decision isn't accidentally re-litigated (or accidentally reverted) without seeing the
tradeoff that was already weighed.

These are records of decisions, not a second copy of the architecture description - see
`docs/ARCHITECTURE.md` for how the system works, `docs/GAP_AUDIT_PHASE0.md` for the audit
findings (referenced below by number) that motivated many of these decisions, and
`docs/RUNBOOK.md` for what to do when one of these subsystems is actually failing in
production.

| ADR | Decision |
|---|---|
| [0001](0001-unify-rag-execution-paths.md) | Unify the three RAG execution paths into one node-function pipeline |
| [0002](0002-circuit-breakers-and-degradation-tiers.md) | Circuit breakers + bounded retry + graceful degradation tiers for Qdrant/Ollama/embeddings |
| [0003](0003-ollama-concurrency-gate.md) | Bound Ollama GPU concurrency with an explicit gate instead of unbounded concurrent requests |
| [0004](0004-redis-caching-fail-open.md) | Redis-backed caching everywhere, fail-open on Redis unavailability |
| [0005](0005-jwt-revocation-and-rotation.md) | JWT jti-based revocation blocklist, refresh token rotation, device binding |
| [0006](0006-field-level-phi-encryption.md) | Field-level encryption for PHI-adjacent columns via a SQLAlchemy TypeDecorator |
| [0007](0007-observability-optional-by-default.md) | OpenTelemetry tracing and Prometheus metrics, both optional and off by default |
| [0008](0008-arq-background-ingestion-with-fallback.md) | arq background job queue for ingestion, with automatic inline fallback |
| [0009](0009-k8s-manifests-exclude-stateful-stores.md) | Kubernetes manifests deliberately exclude stateful data stores |
| [0010](0010-role-based-retrieval-filtering.md) | Role-based retrieval trust-level and document-type filtering |
| [0011](0011-emergency-triage-short-circuit.md) | Deterministic emergency-triage short-circuit ahead of LLM generation |
| [0012](0012-scraper-isolated-from-rag-collection.md) | Scraper/dataset-generation pipeline kept isolated from the live RAG Qdrant collection |
| [0013](0013-mypy-baseline-ratchet.md) | mypy baseline ratchet instead of requiring full strict-mode compliance immediately |
| [0014](0014-bandit-safety-ci-gates.md) | bandit/safety made real, blocking CI gates via documented, time-boxed suppressions |
