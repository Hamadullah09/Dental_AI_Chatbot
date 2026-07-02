# Expo Hosting Roadmap

This plan keeps the uploaded MVP data safe while preparing the project for a live demo.

## Data Safety Rule

Do not delete these runtime assets:

- `dental_ai.db`
- `dental_ai.db-wal`
- `dental_ai.db-shm`
- `uploaded_docs/`
- `qdrant_storage/`
- `.env`
- generated Q&A files such as `Database Q&A.csv`

Before hosting or major ingestion work, run:

```powershell
.\scripts\backup_mvp_data.ps1
```

For a full data backup, run:

```powershell
.\scripts\backup_mvp_data.ps1 -IncludeUploads -IncludeQdrant
```

## Phase 1: Stabilize Local MVP

- Confirm backend, frontend, and Ollama health.
- Re-ingest failed PDFs one at a time.
- Confirm all important PDFs become `Ready`.
- Test English, Roman Urdu, standard RAG, symptom questions, and web search.

## Phase 2: Host On Office PC

- Keep the office PC powered on.
- Disable sleep/hibernate.
- Run Ollama as a service with LAN access.
- Run backend on `0.0.0.0:8002`.
- Run frontend on `0.0.0.0:3001` or production Next.js mode.

## Phase 3: Domain With Cloudflare Tunnel

Recommended domain layout:

- `demo.wtechx.tech` -> frontend
- `api.wtechx.tech` -> backend

Cloudflare Tunnel avoids router port forwarding and gives HTTPS.

On Windows, install and prepare Cloudflare Tunnel:

```powershell
.\scripts\install_cloudflared.ps1
.\scripts\cloudflare_tunnel_login.ps1
.\scripts\cloudflare_tunnel_create.ps1 -TunnelName dental-ai-mvp
```

Then copy:

```text
docs\cloudflared_config_example.yml
```

to:

```text
.cloudflared\config.yml
```

Replace `<TUNNEL-UUID>` and `<USER>` with the values from Cloudflare.

Run the tunnel:

```powershell
.\scripts\cloudflare_tunnel_run.ps1
```

For live frontend testing, start the frontend with:

```powershell
.\scripts\start_frontend.ps1 -Port 3001 -ApiUrl "https://api.wtechx.tech"
```

## Phase 4: Standard + Agentic RAG

```text
User Question
  |
Query Router / Classifier
  |
Simple?
  | yes                 | no
Standard RAG            Agentic RAG
  |                     |
Final Answer            Final Answer
```

Standard RAG handles simple information questions.

Agentic RAG handles symptoms, risk checks, treatment comparisons, follow-up questions, and future tools such as appointments.

## Expo Checklist

- Backup created.
- Office PC plugged in.
- Sleep disabled.
- Backend health OK.
- Frontend loads through domain.
- Ollama `qwen3:14b` reachable.
- Admin login works.
- Chat test set passes.
- Uploaded data still present.
