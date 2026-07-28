# ADR-0009: Kubernetes manifests deliberately exclude stateful data stores

Date: 2026-07-28
Status: Accepted

## Context

Phase 4 (Scalability) called for Kubernetes manifests to support horizontal scaling
beyond the single-office-PC docker-compose deployment. The system depends on four
stateful services: Postgres, Qdrant, Redis, and Ollama (which additionally needs a GPU
node). Writing StatefulSet manifests for all four was in scope for "add Kubernetes
support," but hand-rolling stateful-service manifests is exactly the kind of task that
looks done after a demo and breaks in ways a maintained operator or managed service
already solved (backup/restore, replication, failover, version upgrades).

## Decision

`k8s/` contains manifests only for the stateless application tiers: `api-deployment.yaml`
(FastAPI backend), `worker-deployment.yaml` (arq ingestion worker, see ADR-0008),
`frontend-deployment.yaml` (Next.js), plus `api-hpa.yaml` (autoscaling, see ADR-0003 for
the custom GPU-queue-depth metric it uses) and `ingress.yaml`. Postgres, Qdrant, Redis,
and Ollama are explicitly left to the deployer's choice, with `k8s/README.md` laying out
the real tradeoff for each (managed vs. self-hosted-via-operator vs. single-node) rather
than the manifests silently picking one.

## Consequences

- Someone deploying this to Kubernetes has to make four explicit infrastructure
  decisions (Postgres, Qdrant, Redis, Ollama hosting) rather than getting a
  turnkey-but-fragile all-in-one manifest set. `k8s/README.md` documents what each choice
  actually costs (e.g. Qdrant Cloud vs. self-hosted cluster vs. single-node-with-snapshots,
  and the PHI-scope caution that clinical data - see ADR-0006 - must never reach Qdrant
  regardless of which option is chosen for it).
- This is consistent with the non-negotiable constraint from this hardening pass's brief
  not to swap Qdrant/Ollama for other tools without an explicit evaluation request - the
  manifests don't sneak in an assumption like "Qdrant runs as a StatefulSet in this
  cluster" that would effectively be a deployment-architecture decision made silently.
- The `worker`/`api`/`frontend` Deployments as shipped assume all four stateful
  dependencies are reachable at whatever URL/host the ConfigMap/Secret point to,
  regardless of how they're actually hosted - the manifests are deliberately agnostic to
  that choice.

## Alternatives considered

- **Ship StatefulSet manifests for all four as a "good enough to start" default.**
  Rejected - a raw StatefulSet Postgres or Qdrant with no operator handles failover,
  backup scheduling/testing, or version upgrades manually; shipping this as the
  path-of-least-resistance default risks it becoming the de facto production setup by
  inertia, which is a worse outcome than forcing an explicit choice up front.
- **Use a Helm chart instead of plain manifests, bundling opinionated defaults for the
  stateful stores via subcharts (e.g. Bitnami's Postgres/Redis charts).** Considered and
  deferred, not rejected outright - `k8s/README.md` notes Helm's templating overhead
  isn't clearly worth it yet at this project's current size/environment count, but this
  is exactly the kind of thing that becomes worth it later; revisit if multiple
  environments (staging/prod) with meaningfully different values are ever needed.
