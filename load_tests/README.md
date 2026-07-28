# Load Testing (Phase 4)

`locustfile.py` simulates two user types against the real API:

- `DentalAIUser` (weight 3): mostly `/chat` and `/chat/stream` — the paths that hit
  Ollama, so this is what will actually find the GPU-inference ceiling.
- `AdminUser` (weight 1): admin document/dataset listing — cheap DB-only endpoints, useful
  as a control to confirm the bottleneck really is generation and not something else.

**Bug fixed in this phase**: the login step posted a hardcoded password
(`admin123456`) that never matched the seeded admin account
(`ADMIN_PASSWORD` in `.env`, default `admin123`) — every simulated user was silently
running unauthenticated (401s on every `/chat` call) rather than exercising the real
pipeline. If you ran this before and got suspiciously flat/fast numbers, that's why;
re-run after this fix.

## Running it

```bash
pip install locust
locust -f load_tests/locustfile.py --host http://localhost:8000
```

Then open http://localhost:8089 to set concurrent user count and ramp-up rate, or run
headless:

```bash
locust -f load_tests/locustfile.py --host http://localhost:8000 \
  --headless -u 50 -r 5 --run-time 5m --csv=load_tests/results/run1
```

Make sure `ADMIN_EMAIL`/`ADMIN_PASSWORD` in your running instance's `.env` match what
`locustfile.py` logs in with (defaults: `admin@example.com` / `admin123`).

## What to look for

- **`/chat/stream` p95/p99 latency** and **error rate** as concurrent users increase -
  this is expected to be the first thing to degrade, since Ollama/Qwen2.5-VL inference is
  the single-GPU bottleneck the whole reliability layer (Phase 1's `ConcurrencyGate`,
  circuit breakers) exists to protect.
- **`concurrency_gate_queue_depth{name="ollama"}`** and **`service_busy_total`** in
  Grafana/Prometheus during the run - this tells you directly how many requests are
  queued waiting for a GPU slot vs. being rejected outright, which locust's own latency
  numbers can't distinguish from Ollama itself just being slow.
- **`circuit_breaker_state`** - if it goes to 2 (open) during the run, that's Qdrant or
  Ollama failing hard, not just slow.

## Honesty note

This load test has **not been executed against real target infrastructure** as part of
this work - there is no GPU/Ollama instance available in the environment this hardening
work was done in, only an API contract review and a fix to a bug that would have
invalidated any prior run. Actually running this against your target hardware (with a
real Qwen2.5-VL:7B model loaded) is required before any capacity number in this repo can
be trusted. Record real results (concurrent users supported at your target p95 latency,
the point queue depth starts climbing, tokens/sec observed) in a new
`load_tests/results/<date>.md` once you've run it, and use them to size
`OLLAMA_MAX_CONCURRENT_REQUESTS` and the HPA rules in `k8s/api-hpa.yaml`.
