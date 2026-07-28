# ADR-0003: Bound Ollama GPU concurrency with an explicit gate

Date: 2026-07-28
Status: Accepted

## Context

Ollama serves Qwen2.5-VL:7B (vision) and Qwen3:14b (text) from a single GPU
(RTX 5060Ti, 16GB VRAM per `docs/DEPLOYMENT.md`'s office-PC target). Nothing prevented an
unbounded number of concurrent chat requests from each issuing their own Ollama call
simultaneously - under real concurrent load this either OOMs the GPU or serializes
requests inside Ollama anyway, just without any of them knowing they're queued, so every
concurrent request looked identically slow with no way to tell "the model is genuinely
busy" from "something is wrong."

## Decision

Add `app/core/concurrency.py`: a `ConcurrencyGate` bounding how many requests may hold an
Ollama slot at once (`ollama_max_concurrent_requests`), with `acquire()`/`acquire_async()`
context managers, a `queue_depth` property, and a `ServiceBusyError` raised when the queue
itself is too deep to be worth waiting on. `app/services/llm.py`'s Ollama call paths
(`_generate_ollama`, `_generate_ollama_stream`, `analyze_image`) all acquire the gate
before calling Ollama. The streaming path (`app/core/streaming.py`) emits an explicit
`"queued"` SSE event when a request is waiting on the gate, so the frontend can show "your
request is queued" instead of an unexplained stall. `queue_depth` is exported as a
Prometheus metric and is what `k8s/api-hpa.yaml`'s custom-metric autoscaling rule scales
on (see `k8s/README.md`), rather than scaling on CPU, which tells you nothing about GPU
saturation.

## Consequences

- Concurrent load now degrades predictably: requests queue (visibly, via the `queued`
  event) up to a configured depth, then get a fast, explicit "busy" response instead of
  piling up until something OOMs or times out.
- This is a single-process gate - if the API is ever scaled to multiple replicas (which
  the Kubernetes HPA path in `k8s/api-hpa.yaml` explicitly supports), each replica has its
  own gate, and the *actual* GPU-level concurrency limit is the sum across replicas. This
  is fine as long as all replicas share one Ollama instance and the per-replica limit is
  set conservatively (e.g. total desired concurrency / expected replica count) - it is
  not a distributed rate limiter, and scaling replica count without adjusting the
  per-replica gate value would defeat the point of having it.
- Provides the concrete metric (`queue_depth`) needed for GPU-aware autoscaling, which
  otherwise has no natural signal (GPU utilization isn't a standard Kubernetes metric
  without additional device-plugin tooling).

## Alternatives considered

- **A distributed semaphore (Redis-backed) instead of an in-process gate**, so the limit
  is enforced correctly across replicas without needing to divide it manually. Deferred:
  this project runs single-replica in its current office-PC deployment target, and adding
  a Redis-coordinated semaphore is complexity worth paying for only once/if multi-replica
  API deployment is actually adopted - flagged here rather than built preemptively.
- **Let Ollama's own request queue be the only bound.** Rejected: Ollama's internal
  queue gives the caller no visibility (no queue-depth signal to alert on or autoscale
  against) and no way to fail fast on an excessively deep queue instead of waiting
  indefinitely.
