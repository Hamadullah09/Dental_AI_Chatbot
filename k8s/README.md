# Kubernetes Manifests (Phase 4)

Plain manifests, not a Helm chart — the project is small enough that Helm's templating
overhead isn't clearly worth it yet; revisit if you need multiple environments (staging/
prod) with meaningfully different values, which is where Helm starts paying for itself.

## What's here

| File | What it deploys |
|---|---|
| `namespace.yaml` | the `dental-ai` namespace |
| `configmap.yaml` | non-secret env vars |
| `secret.yaml.example` | **template only** — copy to `secret.yaml`, fill in real values, never commit the filled version |
| `api-deployment.yaml` | FastAPI backend (Deployment + Service + PVC for uploads) |
| `api-hpa.yaml` | autoscaling for the backend — CPU **and** Ollama queue depth |
| `worker-deployment.yaml` | arq ingestion worker (Deployment + HPA) |
| `frontend-deployment.yaml` | Next.js frontend (Deployment + Service + HPA) |
| `ingress.yaml` | TLS termination + routing (assumes ingress-nginx + cert-manager) |

Apply in order: `kubectl apply -f k8s/namespace.yaml -f k8s/configmap.yaml -f k8s/secret.yaml -f k8s/api-deployment.yaml -f k8s/api-hpa.yaml -f k8s/worker-deployment.yaml -f k8s/frontend-deployment.yaml -f k8s/ingress.yaml`

## Deliberately NOT included: Postgres, Qdrant, Redis, Ollama manifests

Hand-rolling StatefulSets for stateful data stores in raw YAML is exactly the kind of
thing that goes wrong in ways a maintained Helm chart or managed service already solved.
Pick one path per dependency and be deliberate about it — don't silently default to
self-hosted StatefulSets:

- **Postgres**: managed (RDS/Cloud SQL/Azure Database) for anything holding PHI (see
  docs/COMPLIANCE.md) is the strong recommendation — you get backups, point-in-time
  recovery, and encryption-at-rest for free. If self-hosting, use the
  [CloudNativePG](https://cloudnative-pg.io/) operator, not a raw StatefulSet.
- **Redis**: managed (ElastiCache/Memorystore) or the
  [Bitnami Redis Helm chart](https://github.com/bitnami/charts/tree/main/bitnami/redis)
  with sentinel/replication enabled if you need HA. Everything here already fails open
  when Redis is unreachable (rate limiting, idempotency, caching), so a single-node Redis
  is a reasonable starting point — just know what degrades if it goes down (checked in
  `docs/RUNBOOK.md`).
- **Ollama**: needs a GPU node pool; this is infrastructure-specific enough (which cloud,
  which GPU SKU, node pool taints/tolerations) that a generic manifest here would be
  actively misleading. Point `OLLAMA_BASE_URL` at wherever it actually runs.

## Qdrant: single-node vs. clustered — the actual tradeoff

At 37K+ chunks and growing (per the architecture doc), Qdrant is a single point of
failure today. Options, roughly in order of operational simplicity:

1. **Qdrant Cloud (managed)** — simplest, handles clustering/backups/upgrades for you.
   Tradeoff: data leaves your infrastructure, recurring cost, and you're depending on
   their SLA. Given finding #6 (this product now stores real PHI-adjacent clinical
   data), confirm Qdrant Cloud's own compliance posture (BAA availability, data
   residency) before choosing this for anything beyond the public dental-education
   corpus — do NOT let PHI touch Qdrant regardless (PHI already lives in Postgres, encrypted -
   Qdrant should only ever hold document/chunk embeddings, never patient records; verify
   nothing in the ingestion path accidentally sends PHI to Qdrant before choosing a
   managed vendor).
2. **Self-hosted Qdrant cluster** (3+ nodes, replication factor 2-3) — full control, no
   data leaves your infra, but you own upgrades/backups/monitoring. Qdrant's own
   [distributed deployment docs](https://qdrant.tech/documentation/guides/distributed_deployment/)
   cover the actual manifests; this repo doesn't duplicate them since they're
   version-specific and better maintained upstream.
3. **Single-node with scheduled snapshots** (current de-facto state) — acceptable only if
   a Qdrant outage degrading to `keyword_only` retrieval (Phase 1's degradation tier,
   already implemented) is tolerable for your uptime target, and snapshots are actually
   being taken and tested for restore. Confirm this is a deliberate choice, not an
   accident.

This project doesn't decide between these for you — it's a cost/ops-maturity tradeoff,
flagged rather than picked.

## HPA custom metric: Ollama queue depth

`api-hpa.yaml` references a custom metric `dental_ai_ollama_queue_depth`, sourced from
the Prometheus metric `concurrency_gate_queue_depth{name="ollama"}` (Phase 1/3). This
requires [prometheus-adapter](https://github.com/kubernetes-sigs/prometheus-adapter)
installed in-cluster with a rule roughly like:

```yaml
rules:
  custom:
    - seriesQuery: 'concurrency_gate_queue_depth{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "concurrency_gate_queue_depth"
        as: "dental_ai_ollama_queue_depth"
      metricsQuery: 'avg(<<.Series>>{<<.LabelMatchers>>}) by (<<.GroupBy>>)'
```

This is a real, separate cluster addition — install and verify
`kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1` lists the metric before relying on
`api-hpa.yaml`'s Pods metric block. If you haven't set this up, the HPA still works as a
CPU-only autoscaler (delete or comment out that metric block).
