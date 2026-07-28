# Runbook

Phase 7. Operational playbooks for the failure scenarios this hardening pass specifically
built detection and degradation for. Each scenario lists: how you'd notice, how to
confirm, what to do, and how to tell it's resolved. Alert names reference
`monitoring/alert_rules.yml`; metric names reference `app/middleware/metrics.py` and the
Phase 1-5 instrumentation described in `docs/adr/`. See `docs/adr/` for *why* each
subsystem behaves the way it does, and `docs/COMPLIANCE.md` if an incident involves
PHI-adjacent data (`Prescription`/`DentalRecord` rows - see
[ADR-0006](adr/0006-field-level-phi-encryption.md)).

Start every incident at `GET /api/health` - it reports `status`, flat `backend`/`ollama`/
`qdrant` fields, and a nested `checks` object (`app/routers/health.py`). It's the fastest
way to confirm which dependency is actually the problem before diving into any scenario
below.

## Ollama down / unreachable

**Symptoms**: `CircuitBreakerOpen{name="ollama"}` fires (`monitoring/alert_rules.yml`).
`GET /api/health`'s `ollama` field reports non-`ok`. Chat requests either fail fast with
an `OllamaCircuitOpenError`-derived error, or (if the breaker hasn't tripped yet) requests
are slow and timing out one by one first.

**Confirm**:
1. `GET /api/health` - check the `ollama` field's detail.
2. From the API container/host: `curl $OLLAMA_BASE_URL/api/tags` (lists loaded models) -
   distinguishes "Ollama process is down" from "Ollama is up but the model isn't loaded/
   pulled" from "network path between API and Ollama is broken" (common cause on
   Windows/Docker Desktop: `host.docker.internal` resolution - see
   `docs/GAP_AUDIT_PHASE0.md`'s Ollama networking note).
3. Check GPU state on the Ollama host: `nvidia-smi` - OOM or a hung process shows up here.

**Mitigate**:
- If Ollama process crashed: restart it (`docker-compose restart ollama`, or the
  equivalent for however it's deployed - `docs/DEPLOYMENT.md`).
- If GPU OOM: check what else is competing for VRAM; consider reducing
  `OLLAMA_NUM_GPU_LAYERS` (`docs/DEPLOYMENT.md`'s Performance Tuning section) or the
  `ollama_max_concurrent_requests` setting ([ADR-0003](adr/0003-ollama-concurrency-gate.md))
  if concurrent requests are the trigger.
- While Ollama is down, chat traffic fails fast rather than hanging (the circuit breaker
  is doing its job - [ADR-0002](adr/0002-circuit-breakers-and-degradation-tiers.md)).
  Retrieval-only features (search, browsing existing sessions) remain unaffected since
  they don't depend on Ollama.
- The emergency-triage short-circuit ([ADR-0011](adr/0011-emergency-triage-short-circuit.md))
  still works even with Ollama fully down, since it never calls the LLM - if you need to
  confirm the product is still safe to leave running during an Ollama outage, this is why
  it is.

**Resolved when**: `circuit_breaker_state` for `ollama` returns to closed (0) - it
self-recovers once a half-open probe succeeds after Ollama is reachable again; no manual
reset needed.

## Qdrant degraded / down

**Symptoms**: `RetrievalDegradedNotFullHybrid` fires (`retrieval_degradation_total`
incrementing). `CircuitBreakerOpen{name="qdrant"}` may also fire. `GET /api/health`'s
`qdrant` field is non-`ok`. Answers are still being generated but citing fewer/different
sources than usual, or `state.degradation_tier` in a chat response's trace log shows
`keyword_only` instead of `full_hybrid`.

**Confirm**:
1. `GET /api/health` - `qdrant` field detail.
2. If self-hosted: check the Qdrant container/process is up and its data volume has
   free disk space (Qdrant fails in unusual ways when its storage volume is full, not
   always with an obvious "disk full" error).
3. If Qdrant Cloud or another managed instance: check its own status page/console first.

**Mitigate**:
- This is the scenario [ADR-0002](adr/0002-circuit-breakers-and-degradation-tiers.md)'s
  degradation tiers exist for: retrieval automatically falls back to pure BM25 keyword
  search over Postgres (`app/services/degradation.py`'s `keyword_only_retrieve()`), so
  chat keeps answering, just with lower retrieval quality - no immediate action is
  required to keep the product up.
- If Qdrant is down long enough that even `keyword_only` isn't landing well, the
  `cached_answer`/`static_degraded` tiers serve a previously-successful answer for
  repeated questions rather than nothing - check `retrieval_degradation_total{tier=...}`
  to see which tier traffic has settled into.
- Fix the underlying Qdrant issue (restart, free disk space, restore from snapshot -
  `k8s/README.md`'s Qdrant section covers the single-node-vs-clustered tradeoff if this
  keeps recurring).

**Resolved when**: `retrieval_degradation_total`'s rate returns to zero and
`circuit_breaker_state{name="qdrant"}` is closed. Spot-check a chat answer's sources to
confirm citations are back to normal document names, not degraded-tier fallbacks.

## Latency spike (p95 API latency high)

**Symptoms**: `HighAPILatencyP95` fires (p95 request latency over 5s for 5+ minutes).

**Confirm, in this order** (cheapest checks first):
1. `OllamaQueueDepthHigh` - is this GPU contention? If `concurrency_gate_queue_depth{name="ollama"}`
   is elevated, requests are legitimately queued for a GPU slot
   ([ADR-0003](adr/0003-ollama-concurrency-gate.md)), not stuck.
2. Check `CircuitBreakerOpen` for any dependency - a half-open breaker repeatedly probing
   a still-recovering dependency can add latency without being fully "down."
3. If neither above explains it, turn on tracing (`OTEL_ENABLED=true`, point
   `otel_exporter_endpoint` at a running collector - see
   [ADR-0007](adr/0007-observability-optional-by-default.md)) and trace one slow request
   end to end: retrieval, reranking, context building, and generation are each their own
   traced span (`app/services/vector_store.py`'s `ResilientQdrantClient`,
   `app/services/observability.py`) - this tells you *which* step is actually slow
   instead of guessing.
4. Check Redis - if caching (retrieval/embedding/memory-context, see
   [ADR-0004](adr/0004-redis-caching-fail-open.md)) is failing open due to a Redis
   outage, every request recomputes from source, which reads as a latency regression
   with no single obvious cause.

**Mitigate**:
- GPU-bound (queue depth high, Ollama itself fine): raise
  `ollama_max_concurrent_requests` if VRAM allows, or scale out via the Kubernetes HPA
  path (`k8s/api-hpa.yaml`, [ADR-0003](adr/0003-ollama-concurrency-gate.md)) if running on
  Kubernetes rather than the single-office-PC docker-compose target.
- Retrieval-bound (tracing shows Qdrant spans are slow): check Qdrant's own resource
  usage; consider whether the collection has grown enough to need the clustering
  discussion in `k8s/README.md`.
- Redis down: fix Redis; the system keeps working without it (by design - see
  [ADR-0004](adr/0004-redis-caching-fail-open.md)), just slower.

**Resolved when**: p95 latency drops back under the alert threshold and stays there for
the alert's `for: 5m` window.

## Citation verification pass rate drop

**Symptoms**: `CitationVerificationTrimRateHigh` fires -
`citation_verification_total{result="trimmed"}` is more than 15% of all verification
outcomes over a 30-minute window.

**This is a product-quality signal, not an infra outage** - nothing is "down," but a
rising trim rate means the LLM is generating claims the retrieved context doesn't
support at a higher rate than usual, which is exactly the class of problem the
non-negotiable "never relax citation verification" constraint exists to catch, not paper
over.

**Confirm**:
1. Check whether this correlates with a recent deploy (code change) or a recent Ollama
   model version change ([docs/DEPLOYMENT.md](DEPLOYMENT.md)'s Ollama model-swap
   playbook) - a prompt regression or a worse-behaving model version are the two most
   likely causes.
2. Check `retrieval_degradation_total` at the same time window - if retrieval was
   degraded (keyword-only, cached-answer tiers), lower-quality retrieved context makes
   generation more likely to produce claims the (worse) context can't support even
   without any change to the model or prompt. Rule this out before assuming a model/prompt
   regression.
3. Run `python scripts/evaluate_rag.py` (or `scripts/ci_retrieval_gate.py`) against
   `docs/evaluation_dataset.jsonl` to get a controlled, reproducible pass-rate number
   rather than relying on live-traffic sampling alone.
4. Pull a handful of recent `citation_verifier` trace-log entries
   (`state.trace_log`, node `"citation_verifier"`) for `result="trimmed"` cases and read
   the actual removed sentences - is the model fabricating specifics (wrong dosages, wrong
   procedure names) or just phrasing things in a way the lexical-overlap check
   (`app/agent/nodes/citation_verifier.py`'s `_check_citation_support()`, ~40% word
   coverage) doesn't recognize as supported? These need different fixes.
5. Be aware of the short-answer edge case documented in
   `tests/test_rag_pipeline_integration.py`'s
   `test_short_hallucinated_answer_is_flagged_but_not_edited`: an answer with 3 or fewer
   sentences remaining after trimming is flagged (counted in this same metric as
   `flagged_but_kept`) but not edited - if you're seeing `flagged_but_kept` specifically
   rise (not `trimmed`), the unsupported content is reaching users unedited, which is a
   more urgent variant of this same alert and worth checking even though the current
   alert rule only watches `trimmed`.

**Mitigate**:
- If it's a retrieval-degradation side effect: fix the underlying Qdrant/degradation
  issue (see that scenario above) rather than touching citation verification itself.
- If it's a genuine model/prompt regression: **do not relax
  `_check_citation_support()`'s coverage threshold or disable verification to "fix" the
  alert** - that inverts the safety property the alert exists to protect. Instead, revert
  the triggering change (prompt or model version), or, if it's a newly-swapped Ollama
  model, follow `docs/DEPLOYMENT.md`'s rollback guidance (revert `OLLAMA_MODEL` to the
  previous tag, which stays pulled specifically for this reason).
- If the lexical-overlap check itself is producing false positives/negatives at scale
  (e.g. legitimate paraphrasing getting trimmed), that's a genuine improvement to
  consider - but it's a product/policy decision about how strict citation verification
  should be, to be made deliberately with the product owner, not adjusted reactively
  during an alert to make it stop firing.

**Resolved when**: the trim rate returns under 15% *and* you know why it spiked (a
retrieval blip that resolved on its own is a different resolution than "we reverted a
regression") - closing this alert without understanding the cause risks it recurring
silently.
