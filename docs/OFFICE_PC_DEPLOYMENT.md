# Office PC Deployment Guide

This guide runs Dental AI on the office PC with Docker Compose, Qdrant, Ollama, and Cloudflare Tunnel.

## Target Architecture

```text
Internet
  -> Cloudflare Tunnel on office PC
     -> Frontend container: http://localhost:3001
     -> Backend container:  http://localhost:8002
        -> Qdrant container: http://qdrant:6333
        -> Ollama on host:   http://host.docker.internal:11434
```

Do not expose Ollama port `11434` to the public internet. Keep it available only on the office PC/LAN/Tailscale.

## 1. Install Requirements

Install on the office PC:

- Git
- Docker Desktop
- Cloudflared
- Tailscale
- AnyDesk
- Ollama

Confirm:

```powershell
git --version
docker version
docker compose version
cloudflared --version
ollama list
```

## 2. Clone The Repository

```powershell
cd C:\Users\HP\OneDrive\Desktop
git clone https://github.com/Hamadullah09/Dental_AI_Chatbot.git
cd Dental_AI_Chatbot
```

## 3. Create Local Environment File

Copy the example:

```powershell
copy .env.example .env
```

Edit `.env` on the office PC:

```env
ENVIRONMENT=production
CORS_ORIGINS=https://demo.wtechx.tech,https://api.wtechx.tech,http://localhost:3001,http://127.0.0.1:3001

DATABASE_URL=postgresql+psycopg://dental:CHANGE_THIS_PASSWORD@postgres:5432/dental_ai
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD

QDRANT_URL=http://qdrant:6333
QDRANT_LOCAL_PATH=
QDRANT_COLLECTION=dental_docs_clean

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:14b
OLLAMA_VISION_MODEL=qwen2.5vl:7b

JWT_SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET
ADMIN_EMAIL=your-admin-email@example.com
ADMIN_PASSWORD=CHANGE_THIS_ADMIN_PASSWORD
```

Keep `.env` private. It is ignored by Git.

## 4. Start Ollama Models

On the office PC:

```powershell
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama list
```

Ollama can stay bound locally. Do not publish port `11434` through Cloudflare.

## 5. Run Docker Compose

```powershell
docker compose up -d --build
docker compose ps
```

Health checks:

```powershell
curl http://127.0.0.1:8002/api/health
curl http://127.0.0.1:3001
curl http://127.0.0.1:6333/collections
```

## 6. Rebuild Or Restore Qdrant Data

If the office PC has no vectors yet, re-ingest/rebuild the clean collection:

```powershell
.run_venv\Scripts\python.exe scripts\rebuild_clean_qdrant.py --target-collection dental_docs_clean --apply --replace-target
```

If using only Docker services and no local venv, run ingestion from your normal backend environment first, or add a one-off worker container later.

## 7. Cloudflare Tunnel

Login once:

```powershell
cloudflared tunnel login
```

Create tunnel:

```powershell
cloudflared tunnel create dental-ai-office
```

Create config file:

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: C:\Users\HP\.cloudflared\YOUR_TUNNEL_ID.json

ingress:
  - hostname: demo.wtechx.tech
    service: http://localhost:3001
  - hostname: api.wtechx.tech
    service: http://localhost:8002
  - service: http_status:404
```

Add DNS routes:

```powershell
cloudflared tunnel route dns dental-ai-office demo.wtechx.tech
cloudflared tunnel route dns dental-ai-office api.wtechx.tech
```

Run tunnel:

```powershell
cloudflared tunnel run dental-ai-office
```

Install as service:

```powershell
cloudflared service install
```

## 8. Auto Start

Docker services already use:

```yaml
restart: unless-stopped
```

Enable Docker Desktop startup in Docker Desktop settings.

For Ollama, install/run it as a service or add it to Windows startup. Verify after reboot:

```powershell
curl http://127.0.0.1:11434/api/tags
```

Cloudflare Tunnel should be installed as a service. Verify:

```powershell
Get-Service cloudflared
```

## 9. Disable Sleep, Suspend, Hibernate

Run PowerShell as Administrator:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /hibernate off
powercfg /change monitor-timeout-ac 0
```

Also check Windows Settings:

Power & battery -> Screen and sleep -> set sleep to Never.

## 10. BIOS Power Restore

In BIOS/UEFI, enable:

- Restore on AC Power Loss
- Power On after Power Failure
- AC Back / Always On

The exact name depends on motherboard vendor.

## 11. UPS And Remote Access

Use UPS for:

- Office PC
- Router
- ISP modem/ONT

Keep remote access:

- Tailscale for private SSH/RDP/API access
- AnyDesk for emergency GUI access

## 12. Safety Rules

- Do not expose `11434` publicly.
- Do not commit `.env`, tunnel credentials, databases, uploaded PDFs, extracted visuals, or Qdrant storage.
- Cloudflare should expose only frontend and backend.
- Use `/api/health` for lightweight health checks. It should not run model inference or query Qdrant.
