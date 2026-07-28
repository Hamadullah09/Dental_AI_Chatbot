# ADR-0002: Circuit breakers + bounded retry + graceful degradation tiers for Qdrant/Ollama/embeddings

Date: 2026-07-28
Status: Accepted

## Context

Before this pass, a Qdrant or Ollama outage had no defined failure mode: requests would
hang until whatever HTTP client timeout eventually fired (which for Qdrant defaulted to
the same value used for normal operations - `docs/GAP_AUDIT_PHASE0.md`'s later health-check
finding caught this same class of bug in `app/routers/health.py`), retries (where they
existed at all) had no backoff, and there was no way for the system to notice "Qdrant has
been down for 30 seconds, stop hammering it" versus "this one request happened to fail."

## Decision

Add `app/core/resilience.py`: a `CircuitBreaker` class (closed/open/half-open) and a
`retry_with_backoff()` helper with jittered exponential backoff, plus per-dependency
transient-error predicates (`is_transient_network_error`, `is_transient_qdrant_error`).
Three module-level breaker singletons (`qdrant_breaker`, `ollama_breaker`,
`embedding_breaker`) are wired into `ResilientQdrantClient` (transparent proxy in
`app/services/vector_store.py`), `LLMService`'s Ollama calls (`app/services/llm.py`), and
`ResilientEmbeddingModel` (`app/services/embeddings.py`) respectively.

On top of that, `app/services/degradation.py` defines four explicit tiers
(`full_hybrid` -> `keyword_only` -> `cached_answer` -> `static_degraded`): when the
Qdrant breaker is open, `retrieve_chunks` (`app/agent/graph.py`) falls back to pure BM25
retrieval over Postgres instead of failing the whole request, and a previously-cached
successful answer can be served under `cached_answer`/`static_degraded` when even that
isn't possible. `state.degradation_tier` is tracked per-request and exported as a metric
(`RETRIEVAL_DEGRADATION_TOTAL`, Phase 3) so degraded-quality answers are visible to
operators, not silently indistinguishable from normal ones.

## Consequences

- A Qdrant or Ollama outage now fails fast (breaker opens after a configured threshold)
  instead of every concurrent request hanging until timeout, and recovers automatically
  once the breaker's half-open probe succeeds.
- Users get a lower-quality-but-real answer (keyword-only retrieval, or a cached prior
  answer) during a partial outage instead of a hard error, which matters for a product
  answering health-adjacent questions - but this means "the answer looks normal" is no
  longer proof the full hybrid pipeline ran; anyone debugging answer quality has to check
  `degradation_tier` in the trace log or the Grafana dashboard, not just eyeball the
  response.
- Retry budgets are deliberately short (2 attempts, sub-second backoff for embeddings; a
  few seconds total for Qdrant) - this is a UX-latency tradeoff, not a "retry until it
  works" policy. A dependency that's actually down should surface as degraded, not as a
  slow request.

## Alternatives considered

- **A service mesh / sidecar (e.g. Envoy, Linkerd) providing circuit breaking at the
  network layer instead of in application code.** Rejected as a new infra dependency
  requiring its own evaluation (see `docs/DEPLOYMENT.md`'s blue-green section, which
  flags the same category of decision for canary traffic-shifting) - the in-process
  approach needed no new infrastructure and is portable across the docker-compose and
  Kubernetes deployment paths this project supports.
- **Retry indefinitely with backoff instead of a circuit breaker.** Rejected - this
  degrades to the same "requests hang until something else times out" problem under a
  sustained outage, just with extra steps; a circuit breaker's explicit open state is
  what actually bounds latency during an outage.
