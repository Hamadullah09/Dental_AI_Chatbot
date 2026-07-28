# Dental AI Chatbot - Deployment Guide

## Prerequisites

### Office PC (GPU Server)
- **OS**: Windows 10/11 or Ubuntu 22.04
- **GPU**: NVIDIA RTX 5060Ti (16GB VRAM)
- **RAM**: 32GB+ recommended
- **Storage**: 100GB+ free space
- **Software**: Docker Desktop, NVIDIA Container Toolkit

### Network
- Static IP or Dynamic DNS (e.g., DuckDNS)
- Port forwarding: 80, 443
- Cloudflare account (for SSL)

## Step 1: Install Docker Desktop

1. Download Docker Desktop for Windows
2. Enable WSL 2 backend
3. Install NVIDIA Container Toolkit:
   ```bash
   # Run in PowerShell as Administrator
   wsl --install
   # Restart computer
   # Then in WSL:
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

## Step 2: Clone Repository

```bash
git clone https://github.com/Hamadullah09/Dental_AI_Chatbot.git
cd Dental_AI_Chatbot
```

## Step 3: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env
```

### Critical Environment Variables

```bash
# Database
DATABASE_URL=postgresql+psycopg://dental:YOUR_PASSWORD@postgres:5432/dental_ai
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD

# JWT
JWT_SECRET_KEY=YOUR_32_CHAR_SECRET

# Admin
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD

# CORS (add your domains)
CORS_ORIGINS=https://yourdomain.com,http://localhost:3000

# Ollama (office PC IP)
OLLAMA_BASE_URL=http://HOST_IP:11434
```

## Step 4: Start Services

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

## Step 5: Pull Ollama Models

```bash
# On the office PC with GPU
docker exec -it ollama ollama pull qwen2.5-vl:7b
docker exec -it ollama ollama pull qwen3:14b
```

## Step 6: Configure Cloudflare

1. Add domain to Cloudflare
2. Enable SSL (Full mode)
3. Create DNS A record pointing to your public IP
4. Enable Page Rules for caching

## Step 7: Port Forwarding

On your router:
1. Forward port 80 → office PC IP:80
2. Forward port 443 → office PC IP:443

## Step 8: Verify Deployment

```bash
# Check health endpoint
curl https://yourdomain.com/api/health

# Should return:
# {"status": "healthy", "database": "connected", "qdrant": "connected"}
```

## Troubleshooting

### Docker Won't Start
```bash
# Check Docker service
Get-Service docker

# Restart Docker
Restart-Service docker
```

### GPU Not Detected
```bash
# Verify NVIDIA driver
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### API Not Responding
```bash
# Check API logs
docker-compose logs api

# Common issues:
# - Database connection failed
# - Qdrant not ready
# - Redis connection refused
```

### Frontend Can't Connect
```bash
# Check CORS settings in .env
# Ensure your domain is in CORS_ORIGINS

# Check Nginx config
docker-compose logs nginx
```

## Backup & Restore

### Backup
```bash
# Database backup
docker-compose exec postgres pg_dump -U dental dental_ai > backup_$(date +%Y%m%d).sql

# Full backup script
python -c "
from app.services.security import SecurityManager
sm = SecurityManager()
sm.backup_database()
"
```

### Restore
```bash
# Database restore
cat backup_20240101.sql | docker-compose exec -T postgres psql -U dental dental_ai
```

## Performance Tuning

### GPU Memory
```bash
# Monitor GPU usage
nvidia-smi

# Adjust Ollama model layers
# In .env:
OLLAMA_NUM_GPU_LAYERS=35  # For RTX 5060Ti
```

### Database
```bash
# Optimize PostgreSQL
# In docker-compose.yml, add to postgres command:
command: >
  --shared_buffers=4GB
  --effective_cache_size=12GB
  --work_mem=16MB
  --maintenance_work_mem=1GB
```

### Redis
```bash
# Monitor Redis
docker-compose exec redis redis-cli info memory
```

## Blue-Green & Canary Deployment Strategy (Phase 6)

Two very different things get called "deploying a new version" here, and treating them
the same is the mistake to avoid: **application code** (API/worker/frontend containers)
changes on every merge and should be cheap to roll forward and back; an **Ollama model
version change** (e.g. moving to a new Qwen tag) changes the actual answers the product
gives and needs to be validated for quality before real users see it, not just checked
for "does the process start."

### Application code: docker-compose (the office-PC path this doc otherwise describes)

A single GPU box with one docker-compose stack can't do a real blue-green cutover (that
needs two independently-reachable stacks and something in front to shift traffic) or a
traffic-split canary (needs a load balancer / reverse proxy that can weight requests
across two backends). What's practical at this scale, and what the existing CI workflow
(`.github/workflows/ci-cd.yml`'s `deploy` job) currently only gestures at:

1. **Pin image tags to the git SHA, never `:latest`.** `docker-compose build` tagging
   `dental-ai-backend:${{ github.sha }}` (already how the `docker` CI job tags images) is
   necessary but not sufficient — the deploy step also has to reference that same SHA tag
   in the compose file used on the server, not `latest`, or there's nothing concrete to
   roll back *to*.
2. **Keep the previous SHA's compose file around before flipping.** The `deploy` job's
   "Rollback on failure" step currently just echoes
   `docker-compose -f docker-compose.prev.yml up -d` — that file doesn't get written by
   anything today, so as written this rollback step does nothing real. Making it real
   means: before `docker-compose up -d` with the new tag, copy the current
   `docker-compose.yml` (which still references the previous SHA) to
   `docker-compose.prev.yml` on the server, *then* deploy the new one.
3. **Gate the flip on the health endpoint, not just "container started."** Poll
   `GET /api/health` (see `app/routers/health.py` — Phase 3 added flat `backend`/`ollama`/
   `qdrant` fields specifically so a script doesn't have to parse the nested `checks`
   structure) until it reports healthy, or roll back automatically after a timeout,
   instead of the current unconditional `sleep 30`.

This is a real gap in the existing CI/CD workflow, not a hypothetical — flagging it here
rather than silently wiring up a rollback mechanism, since deciding how much automation
vs. manual sign-off a production rollback gets is a product/ops call, not a default I
should make for you.

### Application code: Kubernetes (`k8s/` manifests, Phase 4)

`api-deployment.yaml` already gets a real rolling update for free from the Deployment's
default strategy — worth pinning `maxSurge`/`maxUnavailable` explicitly rather than
relying on the default so a bad rollout can't take available replicas to zero. For an
actual canary (a small % of real traffic on the new version before it gets the rest),
two options, in increasing infra cost:

- **Poor-man's canary, zero new infra**: a second Deployment (`api-canary`) running the
  candidate image at a small replica count, behind the *same* Service as `api-deployment`
  (same `app: dental-ai-api` label). Kubernetes Services load-balance across all matching
  pods roughly evenly per-pod, so replica ratio approximates a traffic percentage (e.g. 1
  canary replica alongside 9 stable ≈ 10% of requests) — imprecise, and you can't target
  specific users/sessions, but it needs nothing beyond what's already in `k8s/`.
- **Real weighted canary**: [Argo Rollouts](https://argo-rollouts.readthedocs.io/) or a
  service mesh (Istio/Linkerd) for precise traffic percentages and automated
  metric-based promotion/rollback (e.g. auto-abort if the canary's error rate or the
  citation-verification pass rate — `citation_verification_total` from Phase 3's metrics —
  regresses). **This is a new infra dependency** in the same category as the
  Redis/Kubernetes/OpenTelemetry-backend additions this hardening pass was told to get
  explicit confirmation on before adding — flagging it rather than wiring it in.

Either way, the LangGraph node-function contract (Phase 0-5's central invariant) means a
canary running old and new code side-by-side is exactly the scenario where an
undocumented change to a node's inputs/outputs would surface as inconsistent behavior
between the two versions — one more reason that constraint stays load-bearing here.

### Ollama model version changes

Model swaps are not stateless-service deploys: the model is what's actually answering
patient/dentist/student questions, and a regression here is a product-quality incident,
not a crash. The existing retrieval/citation quality gate (Phase 5/6 —
`scripts/evaluate_rag.py` + `scripts/ci_retrieval_gate.py`, run against
`docs/evaluation_dataset.jsonl`) is the mechanism to reuse rather than inventing a new one:

1. Pull the candidate model under its **own tag**, don't overwrite the currently-serving
   one: `docker exec -it ollama ollama pull qwen3:14b-<new-version>` alongside the
   existing `qwen3:14b`, so the previous model stays resident and instantly available.
2. Point a scratch/staging `OLLAMA_MODEL` at the new tag and run
   `python scripts/evaluate_rag.py` (or the CI gate script) against it. Do **not** promote
   on a pass rate lower than the currently-deployed model's own last recorded score —
   the non-negotiable constraint that citation verification never gets relaxed "to ship
   faster" applies just as much to a model swap as to a code change.
3. Only after that passes, flip `OLLAMA_MODEL`/`OLLAMA_VISION_MODEL` in `.env` (or the
   k8s ConfigMap) and restart the API — this is the actual cutover, and it's a config
   change, not a redeploy, so it's a one-line revert (`git revert` the env change, or just
   edit it back) if something looks wrong once real traffic hits it.
4. Keep the previous model pulled for at least one full on-call rotation after cutover —
   reverting is "change the env var back and restart," not "re-pull a multi-GB model
   under incident pressure."

### Database migrations during a blue-green/canary window

Any window where old and new application versions can be running against the same
database (a canary, or a blue-green cutover that isn't instantaneous) means Alembic
migrations have to follow expand/contract, not "alter in place": add new/nullable
columns and backfill in the release that introduces a feature, only drop or rename
columns in a *later* release once every instance is confirmed on the new version. This
isn't automatically enforced by Alembic or by anything in this codebase today — it's a
process discipline the team applying these migrations needs to actually follow, flagged
here rather than silently assumed.

## Scaling

For multiple users:
1. Increase `DB_POOL_SIZE` in .env
2. Add Redis cluster
3. Use multiple Ollama instances behind load balancer
4. Consider Kubernetes for high availability
