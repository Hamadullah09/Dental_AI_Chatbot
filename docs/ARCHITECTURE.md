# Dental AI Chatbot - Architecture

## System Overview

Dental AI Chatbot is a production-ready RAG (Retrieval-Augmented Generation) system that answers dental questions using uploaded PDF documents and a vision-capable LLM.

## High-Level Architecture

```
Internet → Cloudflare (SSL/DNS) → Nginx (Reverse Proxy) → Frontend (Next.js) + Backend (FastAPI)
                                                                   ↓
                                              PostgreSQL + Qdrant + Redis + Ollama
```

## Docker Compose Services (8 containers)

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI backend with LangGraph agent |
| `frontend` | 3000 | Next.js 14 React app |
| `postgres` | 5432 | PostgreSQL 16 database |
| `qdrant` | 6333 | Qdrant vector database |
| `redis` | 6379 | Redis 7 cache + sessions |
| `nginx` | 80/443 | Nginx reverse proxy |
| `prometheus` | 9090 | Prometheus metrics |
| `grafana` | 3001 | Grafana dashboards |

## Backend Architecture (FastAPI)

### Request Flow
1. **Authentication** → JWT access + refresh tokens
2. **Rate Limiting** → Redis-based per-IP throttling
3. **Intent Detection** → Classifies query (emergency, symptom, treatment, visual, direct)
4. **Query Rewriting** → Expands dental terms (e.g., "tooth ache" → "dental pain pulpitis")
5. **Hybrid Retrieval** → Vector search (Qdrant) + BM25 keyword search
6. **Visual Retrieval** → Finds related images, diagrams, x-rays
7. **Cross-Encoder Reranking** → Reranks chunks by relevance
8. **Context Building** → Assembles retrieved chunks into LLM prompt
9. **LLM Generation** → Qwen2.5-VL:7B via Ollama (or cloud API)
10. **Citation Verification** → Validates sources are actually cited
11. **Response Formatting** → Adds disclaimer, sources, metadata

### LangGraph Workflow
```
detect_intent → can_answer_directly?
                    ├─ yes → generate_direct_answer → format_response
                    └─ no → rewrite_query → retrieve_chunks → retrieve_visuals → rerank_results
                                                                              ↓
                                                            has_enough_evidence?
                                                                              ├─ yes → build_context → generate_answer → validate_citations → format_response
                                                                              └─ no → search_more → (enough? → build_context | uncertain → respond_with_uncertainty)
```

### Key Services

| Service | File | Purpose |
|---------|------|---------|
| `RAGService` | `app/services/rag.py` | Core RAG pipeline (2400+ lines) |
| `LLMService` | `app/services/llm.py` | Ollama/OpenAI integration, with circuit breaker/retry/GPU concurrency gate (Phase 1) |
| `IngestionService` | `app/services/ingestion.py` | PDF parsing, chunking, embedding |
| `VisualPipeline` | `app/services/visual_pipeline.py` | Image OCR and classification |
| `SecurityManager` | `app/services/security.py` | Input sanitization, backups |
| `EvaluationPipeline` | `app/services/evaluation.py` | RAG quality metrics; `scripts/evaluate_rag.py` / `scripts/ci_retrieval_gate.py` are the runnable entry points (Phase 5) |
| `MemoryService` | `app/services/memory.py` | User preferences, topic tracking, cached in Redis (Phase 4) |

Removed as part of the production-hardening pass (confirmed zero call sites anywhere in
the codebase before deletion): `ModelRouter` (`app/services/model_router.py`),
`CrossEncoderReranker` (`app/services/cross_encoder.py`), and the Redis-backed
`MemoryManager` (`app/agent/nodes/memory.py`, which duplicated `MemoryService`'s job with
an incompatible parallel preference store). See `docs/GAP_AUDIT_PHASE0.md` findings #11/#13
and the ADRs in `docs/adr/`.

### Data Models (PostgreSQL)

| Table | Purpose |
|-------|---------|
| `users` | User accounts. Roles are `admin` / `dentist` / `student` / `patient` - **not** `hygienist`, which this doc previously (incorrectly) listed; see `app/models.py::UserRole`. Whether `hygienist` should become a real future role or was simply a docs error is an open product question (`docs/GAP_AUDIT_PHASE0.md` finding #3) - not decided here. |
| `documents` | Uploaded/ingested PDFs with metadata (trust_level, document_type, review_status) |
| `document_chunks` | Extracted text chunks (Postgres copy; embeddings live in Qdrant) |
| `document_visuals` | Extracted images/diagrams |
| `chat_sessions` / `messages` | Chat conversations |
| `feedback` | User ratings on answers - surfaced via `GET /admin/feedback` (Phase 5) |
| `refresh_tokens` | Hashed refresh tokens, rotated + revocable (Phase 2) |
| `audit_logs` | Security + PHI-access audit trail (Phase 2 extended this to dental_records/prescriptions reads, not just auth events) |
| `user_memories` | Preferences, frequently-asked topics (Postgres-backed; Redis-cached, see `MemoryService`) |
| `dentists` | Dentist directory profiles - see "Dentist Directory Scraper" below for how these get populated |
| `appointments`, `dental_records`, `prescriptions` | Real clinical scheduling/record data (Phase 0 finding #6) - `dental_records` and `prescriptions`' sensitive text columns are encrypted at rest (`app/core/encryption.py`, Phase 2); see `docs/COMPLIANCE.md` |

### Vector Database (Qdrant)

**One collection** (`QDRANT_COLLECTION`, default `dental_docs`), not two as previously
documented here - text chunks and visual embeddings both live in it, discriminated by a
`payload_type: "text" | "visual"` field (see `app/services/ingestion.py` /
`app/services/visuals.py`). The `QDRANT_VISUAL_COLLECTION` setting (`dental_visuals`) is
dead configuration, referenced nowhere in the codebase - kept only because removing a
setting some external `.env` might still reference isn't free, not because it does
anything (`docs/GAP_AUDIT_PHASE0.md` finding #14).

Dentist-directory search (the "find a dentist" feature) uses a **separate** collection
(`dental_dentists`, `scraper_dentist_qdrant_collection` setting) - it is never read by the
chat/RAG pipeline. See "Dentist Directory Scraper" below.

## Frontend Architecture (Next.js 14)

### Pages
- `/chat` - Main chat interface with streaming
- `/dashboard` - Admin dashboard
- `/upload` - Document upload
- `/login` - Authentication

### Components
- `ChatWindow` - Message display with typing indicator
- `ChatInput` - Input with file upload
- `MessageBubble` - Individual message display
- `AppShell` - Navigation sidebar
- `ErrorBoundary` - React error boundary

## AI Models

| Model | Purpose | VRAM | Location |
|-------|---------|------|----------|
| Qwen2.5-VL:7B | Vision LLM | 5-6 GB | Office GPU (RTX 5060Ti) |
| Qwen3:14b | Text LLM | 9-10 GB | Office GPU (RTX 5060Ti) |
| all-MiniLM-L6-v2 | Embeddings | ~100 MB | Office GPU (CPU fallback) |
| BGE-reranker | Reranking | ~500 MB | Office GPU (CPU fallback) |

## Network Architecture

```
                    ┌─────────────────┐
                    │   Cloudflare    │
                    │  (SSL + DNS)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Nginx       │
                    │ (Rate Limiting) │
                    │ (Security Head) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
      ┌───────▼──────┐ ┌────▼────┐ ┌───────▼──────┐
      │   Frontend   │ │   API   │ │   Grafana    │
      │  (Next.js)   │ │(FastAPI)│ │ (Dashboard)  │
      └──────────────┘ └────┬────┘ └──────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
      ┌───────▼──┐  ┌──────▼──┐  ┌───────▼──┐
      │ Postgres │  │  Qdrant │  │  Redis   │
      │  (Data)  │  │(Vectors)│  │ (Cache)  │
      └──────────┘  └─────────┘  └──────────┘
                            │
                    ┌───────▼───────┐
                    │    Ollama     │
                    │ (Office GPU)  │
                    │ RTX 5060Ti    │
                    └───────────────┘
```

## Security Architecture

1. **Authentication**: JWT access tokens (2h, reduced from 24h in Phase 2 - see
   `app/core/config.py`'s comment on why not shorter yet) + rotating refresh tokens (7d).
   Access tokens are individually revocable via a Redis blocklist
   (`app/core/token_blocklist.py`) - logout and `POST /admin/users/{id}/revoke-sessions`
   both use it, closing the "JWT can't be revoked before expiry" gap.
2. **Authorization**: Role-based (`admin`, `dentist`, `student`, `patient` - see the Data
   Models correction above), enforced server-side on every clinical endpoint.
3. **Rate Limiting**: Per-user **and** per-IP (Phase 2 added per-IP; upload previously had
   no rate limiting at all), sliding window via Redis.
4. **Input Sanitization**: `SecurityManager.sanitize_input()` (bleach-based) is now wired
   into the chat question path (Phase 2) - it existed before but was never called from any
   request handler. Retrieved document content also gets a separate prompt-injection scan
   (`app/agent/nodes/safety.py::neutralize_retrieved_content`).
5. **Security Headers**: CSP, HSTS, X-Frame-Options
6. **Audit Logging**: Auth events, plus PHI access (view/create/update/delete/export) on
   `dental_records` and `prescriptions` (Phase 2 - this did not exist before).
7. **Field-Level PHI Encryption**: `Prescription`/`DentalRecord` sensitive text columns are
   encrypted at rest (Phase 2, `app/core/encryption.py`). `SecurityManager.encrypt_backup()`/
   `decrypt_backup()` exist but are **not wired into any backup script** - encrypted backups
   are aspirational, not implemented; don't assume backups are encrypted without checking
   whatever backup process you actually run.
8. **IP Allowlisting**: `SecurityManager.check_ip_allowlist()` exists but is called from
   nowhere - not an active control despite being listed as one previously. Either wire it
   into a real enforcement point (e.g. an admin-only middleware) or remove it; leaving
   unused security-sounding code around invites exactly this kind of doc/reality drift.

## Monitoring

- **Prometheus**: Request count, latency, LLM performance, retrieval metrics, circuit
  breaker state, GPU concurrency gate queue depth, citation verification outcomes,
  agent-graph fallback rate (`app/middleware/metrics.py`)
- **Grafana**: Dashboards at `monitoring/grafana/dashboards/dental-ai.json`
- **Alertmanager**: `monitoring/alert_rules.yml` (p95 latency, 5xx rate, GPU queue depth,
  circuit breaker open, agent-fallback rate, citation-trim rate) - Slack/PagerDuty routing
  is a template in `monitoring/alertmanager.yml`, commented out pending real credentials
- **Structured Logging**: JSON logs with request IDs
- **OpenTelemetry**: Distributed tracing, off by default (`OTEL_ENABLED=false`) - exports
  to Jaeger when enabled, which runs under the opt-in `observability` Docker Compose
  profile (`docker compose --profile observability up`), not by default

## Data Collection Subsystems (previously undocumented - `docs/GAP_AUDIT_PHASE0.md` finding #7)

Two subsystems exist outside the manual-PDF-upload ingestion path described above. Neither
writes into the `dental_docs` collection the chat/RAG pipeline queries - this was verified,
not assumed, before writing this section.

### Dentist Directory Scraper (`app/scrapers/`, `app/services/scraper/`)

Crawls the Aga Khan University Hospital's public "Find a Doctor" dentistry listing
(`app/scrapers/crawler.py`) - names, specialties, schedules, profile images - for the
in-app "find a dentist" feature (`/dentists` page, `dentists` table). Respects
`robots.txt` by default (`SCRAPER_RESPECT_ROBOTS_TXT=true`) and rate-limits its own
requests (`SCRAPER_REQUEST_DELAY_SECONDS`).

- **Storage**: Postgres `dentists` table + a **separate** Qdrant collection
  (`dental_dentists`, `app/services/scraper/embedding_service.py`) used only for semantic
  dentist-profile search. The chat/RAG pipeline never reads this collection - confirmed by
  reading `RAGService.retrieve()` and every `rerank_chunks()` call site, none of which
  reference `scraper_dentist_qdrant_collection`.
- **Licensing/attribution**: this is a live scrape of a hospital's own public physician
  directory (not republished copyrighted educational content), which is a materially
  different risk profile - but "scraping a hospital's public site is fine" is a policy
  read, not a legal one. Confirm AKU's Terms of Use permit automated collection of this
  data before relying on it in production, and keep the profile data in sync/removable if
  AKU requests it (see `app/services/scraper/sync_service.py` for the re-sync job).
- **Trust/quality review**: not applicable in the sense manual PDF uploads need it (this
  data doesn't feed cited RAG answers), but IS subject to the same PHI/PII handling
  question as any other structured personal data the app stores about real people (see
  `docs/COMPLIANCE.md`) - a scraped dentist's biography/contact info is still PII about a
  real person, even though it's publicly sourced.

### Dataset Generation (`app/services/dataset_generation.py`)

A one-way export tool, **not an ingestion path**: it reads already-approved
`Document`/`DocumentChunk` rows (the same PDFs already trust-reviewed via manual upload)
and uses an LLM to generate synthetic instruction/input/output Q&A pairs from them -
useful for fine-tuning or building an eval set, per the `CATEGORIES` list
(`patient_friendly`, `student_explanation`, `emergency_referral`, etc.). Output goes to
`draft_dental_qa.jsonl` and a review spreadsheet (`Database Q&A.csv`, tracked in git -
confirm before publishing this repo elsewhere that a reviewer hasn't left PHI-adjacent
notes in it) with explicit `correctness`/`safety`/`approved_or_rejected` columns for human
review. Nothing reads `draft_dental_qa.jsonl` or the review CSV back into
`Document`/`DocumentChunk` or Qdrant - confirmed by grepping for both filenames across
the codebase. If that ever changes (e.g. approved synthetic Q&A pairs get ingested as new
"documents"), the same trust-level/review-status gating manual uploads go through must
apply to them too - don't let generated content skip that gate just because it's
LLM-authored rather than scraped.

## Deployment

See `docs/DEPLOYMENT.md` for detailed deployment instructions. Kubernetes manifests are in
`k8s/` (see `k8s/README.md` for the Postgres/Qdrant/Redis/Ollama managed-vs-self-hosted
tradeoffs deliberately left as decisions, not defaults).
