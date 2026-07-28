# ADR-0007: OpenTelemetry tracing and Prometheus metrics, both optional and off by default

Date: 2026-07-28
Status: Accepted

## Context

Before this pass, there was no distributed tracing and limited metrics coverage, making
it hard to answer basic operational questions (where is latency going: retrieval,
reranking, LLM generation? is Qdrant degraded right now? what's the citation
verification pass rate over time?) without reading logs by hand. But this project's
primary deployment target (`docs/DEPLOYMENT.md`) is a single office-PC docker-compose
stack, not a team with an existing observability backend - mandating a tracing backend
(Jaeger, Tempo, etc.) as a hard dependency would be a real infra burden for that
deployment shape.

## Decision

Add OpenTelemetry tracing (`observability.trace_operation()`, used around Qdrant calls in
`ResilientQdrantClient` and elsewhere) gated behind an `OTEL_ENABLED` flag, off by
default - when disabled, `trace_operation()` is a no-op context manager, not a
best-effort-then-silently-degrade wrapper, so there's no ambiguity about whether it's
doing anything. Prometheus metrics (`AGENT_GRAPH_FALLBACK_TOTAL`,
`CITATION_VERIFICATION_TOTAL`, `RETRIEVAL_DEGRADATION_TOTAL`, `RETRIEVAL_HIT_TOTAL`,
`concurrency_gate_queue_depth`, and pre-existing ones) are always-on and cheap
(in-process counters/histograms, no network call), exposed via the existing
`/metrics`-style endpoint for Prometheus to scrape - this doesn't need an opt-in flag
since it has no meaningful operational cost or external dependency at the point of
emission (only the *scraping* side, Prometheus itself, is optional infrastructure someone
chooses to run). `docker-compose.yml`'s `jaeger`/`alertmanager` services are placed under
an opt-in `observability` Compose profile so a bare `docker-compose up` doesn't pull in
either.

## Consequences

- A team that wants tracing gets it by setting one env var and running a backend
  (Jaeger, or any OTLP-compatible collector via `otel_exporter_endpoint`) - a team that
  doesn't want it pays zero runtime cost, not even the overhead of a disabled-but-present
  SDK doing work.
- Metrics work out of the box with zero configuration - `docs/DEPLOYMENT.md`'s office-PC
  path gets useful Grafana dashboards (`monitoring/grafana/dashboards/dental-ai.json`)
  without needing to stand up tracing infrastructure it may never need.
- Anyone debugging a specific slow request will still want tracing (metrics show *that*
  something is slow in aggregate, tracing shows *where* in one specific request) - it's
  worth turning on `OTEL_ENABLED` before investigating a latency incident (see
  `docs/RUNBOOK.md`'s latency-spike scenario) rather than assuming metrics alone will
  pinpoint the cause.

## Alternatives considered

- **Make tracing always-on with a lightweight default exporter (e.g. console/logging
  exporter) instead of a flag.** Rejected - a console exporter for every traced operation
  would flood logs in production without giving anything close to Jaeger's queryable
  trace view; genuinely useful tracing requires a real backend, which is the actual
  infra dependency being gated, not tracing instrumentation itself.
- **Require an observability backend as a mandatory part of the deployment.** Rejected -
  conflicts directly with the office-PC single-box deployment target being this
  project's primary supported path; mandating infra that target doesn't need would be
  scope creep beyond "harden the existing architecture."
