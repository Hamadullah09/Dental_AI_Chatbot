# ADR-0004: Redis-backed caching everywhere, fail-open on Redis unavailability

Date: 2026-07-28
Status: Accepted

## Context

Several read paths are called on every request but change rarely: retrieval results for
a given query+filters combination (`app/services/retrieval_cache.py`), single-text
embeddings (`app/services/embeddings.py`), user memory/preference context
(`app/services/memory.py`), and a last-resort "serve the previous good answer" cache for
degraded-mode responses (`app/services/degradation.py`). None of these were cached before
this pass, meaning every chat turn re-did full retrieval, re-embedded the same repeated
questions, and re-queried Postgres for memory context - real latency and load that scales
linearly with traffic for no reason when the underlying data hasn't changed.

## Decision

Add Redis-backed caching at each of these points, each with its own TTL setting
(`embedding_cache_ttl_seconds`, `memory_context_cache_ttl_seconds`,
`degraded_answer_cache_ttl_seconds`, plus retrieval's own generation-based invalidation -
see the "current_generation()" mechanism in `retrieval_cache.py`, bumped by
`app/services/ingestion.py` on every successful ingestion so stale retrieval results don't
outlive a document re-index). Every cache read/write is wrapped in `try/except: pass`
(the pattern documented and intentionally exempted from bandit's B110 check - see ADR-0014)
so a Redis outage degrades to "every request recomputes from source," never to an error.

## Consequences

- Redis is now load-bearing for performance but never for correctness or availability -
  losing Redis makes the system slower (no caching) but not broken. This is a deliberate
  choice consistent with rate limiting and idempotency also already failing open
  elsewhere in the app.
- Retrieval caching specifically needs generation-based invalidation rather than a flat
  TTL, because serving stale retrieval results after a document re-ingestion would mean
  answers citing a document version that no longer exists in Qdrant - a correctness bug
  for a system whose entire value proposition is grounded, citable answers. A flat TTL
  alone would have been simpler but wrong.
- Degraded-tier results (`keyword_only`, etc.) are deliberately *not* cached under the
  same key as full-hybrid results (see ADR-0002) - caching a degraded answer as if it
  were normal would silently keep serving lower-quality answers long after the underlying
  outage recovered, for the TTL's duration.

## Alternatives considered

- **An in-process (per-worker) cache instead of Redis.** Rejected: with multiple API
  workers/replicas (already supported via the Kubernetes HPA path), an in-process cache
  would have inconsistent hit rates and couldn't be invalidated across workers on
  ingestion - Redis gives one shared, centrally-invalidatable cache.
- **No caching, rely on Qdrant/Postgres/embedding-model performance alone.** Rejected on
  latency/load grounds once GPU-bound embedding and Ollama concurrency (ADR-0003) were
  already identified as the tightest bottleneck - avoiding redundant embedding calls for
  repeated questions directly reduces contention on the same GPU Ollama depends on.
