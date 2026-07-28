# ADR-0008: arq background job queue for ingestion, with automatic inline fallback

Date: 2026-07-28
Status: Accepted

## Context

`app/workers/tasks.py` already contained a fully-built arq worker (`ingest_document_task`,
cleanup jobs, dataset generation, dentist sync) before this pass, but it was never
actually wired up: nothing enqueued a job, and `WorkerSettings.redis_settings` returned an
already-connected aioredis client instance instead of the `arq.connections.RedisSettings`
object arq's worker bootstrap actually expects - meaning `arq worker
app.workers.tasks.WorkerSettings` would have failed immediately on the first real attempt
to run it, had anyone tried. Document ingestion (chunking + embedding a large PDF) ran
inline in the API request's background-task thread pool instead, competing with
request-serving for CPU on the same box that also runs Ollama inference.

## Decision

Fix `_build_redis_settings()` to return the correct `RedisSettings` object, and add
`enqueue_ingestion_job()` / `start_ingestion()` as the actual integration point: upload
routers (`app/routers/chat.py`, `app/routers/admin.py`) call `start_ingestion()`, which
tries to enqueue on the arq worker first and falls back to the previous
in-process-background-task behavior if the queue is unreachable (Redis down, no worker
running) - so wiring up the worker is additive, not a hard new requirement to run one.
`enqueue_ingestion_job()` is hard-bounded with `asyncio.wait_for(timeout=2.0)` on top of
arq's own fast-fail connection settings, specifically because an unresolvable/unreachable
Redis host must not hang the upload request itself waiting to find out the queue is
unavailable - a real bug this pass's own test suite hit (hanging on a bogus "redis"
hostname outside its Docker network) before the timeout was added.

## Consequences

- Large-document ingestion no longer competes with request-serving CPU when a worker is
  running - `docker-compose.yml`'s new `worker` service is what should actually be
  running arq in the deployed stack; if it's not running, uploads still work (inline
  fallback), just with the original CPU-contention tradeoff.
- The router-level `start_ingestion()` wrapper deliberately takes an `inline_fallback`
  callable parameter rather than calling `ingest_document_task` directly on fallback -
  each router's own test suite already monkeypatches its own module-level
  `IngestionService` import (e.g. `app.routers.chat.IngestionService`), and calling the
  worker module's own import directly would silently bypass that mock, running against a
  real, un-mocked `IngestionService` in tests - the same class of "wrong module path
  mocked" bug documented in `docs/GAP_AUDIT_PHASE0.md` finding #1's root cause.
- Operators need to actually run the worker (`arq app.workers.tasks.WorkerSettings`, or
  the `worker` Compose service) for the performance benefit to materialize - the fallback
  means a missing worker fails safe, not silently, but it also means "ingestion works" is
  not proof the worker is running; check `enqueue_ingestion_job.failed` log lines or the
  worker service's own health if ingestion feels slower than expected.

## Alternatives considered

- **FastAPI `BackgroundTasks` only, no separate worker process.** This was the prior
  state - rejected going forward because it has no independent scaling, no retry
  semantics beyond what's hand-rolled, and directly competes with request-handling
  threads for CPU on the same process.
- **Require the arq worker to be running, no inline fallback.** Rejected - would turn a
  Redis/worker outage into a hard upload failure instead of a performance regression,
  which is a worse failure mode for an already-fail-open-by-default codebase (see
  ADR-0004).
