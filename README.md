# Dental AI Chatbot

Professional MVP for a Dental AI Retrieval-Augmented Generation chatbot. The app uses FastAPI, PostgreSQL, Qdrant, PDF ingestion, JWT authentication, role-based admin tools, chat history, source citations, and a professional React/Next.js frontend with light and dark themes.

Dental AI is educational clinical decision support. It does not replace diagnosis, treatment planning, emergency care, or judgment from a licensed dentist.

## Features

- Register and login with JWT authentication.
- Roles: `admin`, `dentist`, `student`, and `patient`.
- Admin PDF upload, document list, delete, re-ingest, ingestion progress, and ingestion logs.
- Production-grade ingestion guardrails: PDF validation, file size checks, encrypted/empty PDF rejection, background processing, and optional OCR fallback.
- PDF parsing with page numbers, chunk indexes, document metadata, and Qdrant point IDs.
- Qdrant vector retrieval with configurable top-k, metadata filtering, hybrid keyword/vector retrieval, reranking, and context compression.
- RAG answers grounded in retrieved dental context, with optional trusted web search only when the chat web-search toggle is enabled.
- Trusted web search through Tavily, Brave, or Google Custom Search configuration, filtered to approved clinical domains.
- Chat document upload for user-scoped PDF questions.
- Voice input in the chat composer through browser microphone speech recognition.
- Dataset Q&A generation from chunks with duplicate-skip logic and CSV export for expert review.
- Citations include document name, page number, chunk index, and score.
- Chat sessions, messages, document records, chunks, and feedback persisted in SQL.
- PostgreSQL and Qdrant via Docker Compose.
- React/Next.js frontend with separate pages for sign in, registration, chat, history, and admin document management.
- ChatGPT-style chat workspace with persistent light/dark theme, source chips, feedback controls, attachment upload, voice input, and web-search toggle.
- Pytest coverage for auth, chat history, feedback, admin upload, and ingestion metadata.
- No hard-coded secrets. Use `.env`.

## Architecture

```mermaid
flowchart LR
  UI["Next.js React UI"] --> API["FastAPI API"]
  API --> PG["PostgreSQL: users, documents, chunks, chats, feedback"]
  API --> RAG["RAG service"]
  API --> ING["PDF ingestion service"]
  ING --> PDF["Uploaded dental PDFs"]
  ING --> QD["Qdrant vector store"]
  RAG --> QD
  RAG --> LLM["OpenAI, Ollama/Qwen, or extractive fallback"]
  RAG --> WEB["Optional trusted web search"]
```

## Quick Start With Docker

1. Copy the environment template.

```bash
cp .env.example .env
```

2. Edit `.env`.

Required for production-like use:

```bash
JWT_SECRET_KEY=replace-with-a-long-random-secret
OPENAI_API_KEY=your-openai-api-key
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:14b
OLLAMA_NUM_CTX=4096
OLLAMA_TIMEOUT_SECONDS=300
DATASET_LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_FALLBACKS=gpt-4.1-mini,gpt-4o-mini,gpt-3.5-turbo
```

If the backend runs inside Docker and Ollama runs on the host machine, use:

```bash
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

For Docker Compose, use the container services:

```bash
DATABASE_URL=postgresql+psycopg://dental:dental_password@postgres:5432/dental_ai
QDRANT_URL=http://qdrant:6333
QDRANT_LOCAL_PATH=
```

`JWT_SECRET_KEY` is not provided by OpenAI, Qdrant, or PostgreSQL. It is your own private random signing secret used by the backend to create and verify login tokens. Generate one locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep this value only in `.env`. Never commit it to GitHub.

For local demos, the app still runs without `OPENAI_API_KEY`; it returns an extractive answer from the top retrieved chunk.

Set the frontend chat timeout to match your model speed:

```bash
NEXT_PUBLIC_BACKEND_HEALTH_TIMEOUT_MS=1500
NEXT_PUBLIC_CHAT_GENERATION_TIMEOUT_MS=300000
```

The app sends a single grounded chat request to `/api/chat`; there is no OpenAI backup route in the main flow. If the backend is healthy but the model is slow, the longer request timeout gives Qwen more time to finish before the UI shows a failure.

Optional trusted web search:

```bash
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=your-tavily-api-key
WEB_SEARCH_TRUSTED_DOMAINS=who.int,cdc.gov,nih.gov,ncbi.nlm.nih.gov,nhs.uk,ada.org,nice.org.uk,fda.gov
```

Web search does not run automatically. The chat UI sends online search requests only when the user enables the web-search toggle. With the toggle off, the chatbot uses local uploaded/PDF knowledge only and says when it does not have enough evidence.

Optional RAG quality modes:

```bash
RAG_MODE=simple
ALLOW_GENERAL_FALLBACK=true
ENABLE_MEMORY=true
ENABLE_QUERY_REWRITING=true
ENABLE_ADJACENT_CHUNK_EXPANSION=true
ENABLE_HYDE=false
ENABLE_SELF_CHECK=false
ENABLE_BGE_RERANKER=false
BGE_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
ENABLE_MULTIMODAL_RAG=true
EXTRACTED_VISUALS_DIR=uploads/extracted_visuals
VISUAL_MIN_RELEVANCE_SCORE=0.95
RETRIEVAL_MIN_RELEVANCE_SCORE=1.1
MULTI_QUERY_MAX_VARIANTS=4
OLLAMA_TOP_P=0.8
```

Supported `RAG_MODE` values are `simple`, `memory`, `multi_query`, `hyde`, `adaptive`, `corrective`, `self_rag`, and `agentic`. The app still starts in stable simple mode by default, with clean chunk filtering, query rewriting, relevance scoring, strict Qwen prompting, adjacent chunk expansion, multimodal visual retrieval, and clearly labeled fallback answers. BGE reranking is optional and only runs when `ENABLE_BGE_RERANKER=true` and the reranker model is available. See `docs/RAG_EVOLUTION_ROADMAP.md` and `docs/MULTIMODAL_RAG.md` for the staged RAG upgrade notes.

3. Start the stack.

```bash
docker compose up --build
```

4. Open the app.

```text
http://localhost:3000
```

5. Sign in as the configured admin.

Admin users are not created through public registration. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`; the backend seeds that admin account into the database on startup.

The FastAPI backend is still available at:

```text
http://localhost:8000
```

## Local Development Setup

Run the backend on macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Run the backend on Windows with the existing local environment:

```powershell
.\.run_venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

For local non-Docker development, set:

```bash
DATABASE_URL=sqlite:///./dental_ai.db
QDRANT_URL=
QDRANT_LOCAL_PATH=qdrant_storage
MAX_UPLOAD_MB=200
EMBEDDING_BATCH_SIZE=64
VECTOR_UPSERT_BATCH_SIZE=128
```

### Fast Local Qdrant Server Mode

Local file-mode Qdrant (`QDRANT_LOCAL_PATH=qdrant_storage`) is convenient for small demos, but it becomes very slow once the collection grows past roughly 20,000 points. For retrieval tuning and the 200-question benchmark, run Qdrant as a Docker server and point the backend to HTTP Qdrant instead.

Start Qdrant only:

```powershell
.\scripts\start_qdrant_docker.ps1
```

Migrate the clean reviewed corpus into the Docker Qdrant server without overwriting the old local collection:

```powershell
.\scripts\migrate_clean_qdrant_to_docker.ps1 -ReplaceTarget
```

Then set the backend environment to use the server collection:

```bash
QDRANT_URL=http://127.0.0.1:6333
QDRANT_LOCAL_PATH=
QDRANT_COLLECTION=dental_docs_clean
```

The migration script rebuilds `dental_docs_clean` from SQL `documents`, `document_chunks`, and `document_visuals`, keeping only reviewed/high or medium trust records, clean text chunks, and indexed visuals. The old local `dental_docs` collection remains untouched.

For scanned/image-only PDFs, install OCR system tools and configure paths when Windows cannot find them automatically:

```bash
OCR_DPI=250
OCR_LANGUAGE=eng
OCR_CONFIG=--psm 6
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
POPPLER_PATH=C:\poppler\Library\bin
```

`TESSERACT_CMD` should point to `tesseract.exe`; `POPPLER_PATH` should point to the folder containing Poppler tools such as `pdftoppm.exe`.

Run the frontend in another terminal on Windows:

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8002"
npm run dev -- -p 3001
```

Then open:

```text
http://127.0.0.1:3001
```

If port `8002` is already in use on Windows, stop the old backend process first:

```powershell
Get-NetTCPConnection -LocalPort 8002 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Offline Ingestion

Place PDFs in `knowledge_base/`, make sure Qdrant is running, then run:

```bash
python ingest.py
```

The script stores document and chunk metadata in SQL and vectors in Qdrant. Each vector payload includes:

- `text`
- `chunk_id`
- `document_id`
- `document_name`
- `canonical_document_title`
- `book_title`
- `author`
- `author_or_source`
- `publisher`
- `year`
- `edition`
- `document_type`
- `trust_level`
- `review_status`
- `specialty`
- `dental_specialty`
- `topic`
- `difficulty_level`
- `language`
- `file_hash`
- `content_hash`
- `section_title`
- `chapter_title`
- `quality_score`
- `is_noisy`
- `noise_reasons`
- `source`
- `page_number`
- `chunk_index`

When `ENABLE_MULTIMODAL_RAG=true`, PDF ingestion also extracts page snapshots, embedded images, figure regions, and tables into `uploads/extracted_visuals/{document_id}/`, stores metadata in `document_visuals`, and indexes visual captions/descriptions in Qdrant with `payload_type="visual"`. If a scanned PDF has no extractable text, the pipeline now keeps going with visual-only indexing instead of failing immediately.

Visual maintenance scripts:

```bash
python scripts/extract_pdf_visuals.py
python scripts/rebuild_visual_index.py
```

## Dataset Q&A Generation

The admin workflow can generate Q&A rows from ingested chunks using the configured dataset provider. For paid OpenAI generation, set:

```bash
DATASET_LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_FALLBACKS=gpt-4.1-mini,gpt-4o-mini,gpt-3.5-turbo
```

Already-generated chunks are skipped so repeated clicks do not duplicate rows. The admin UI can download the expert-review file as `Database Q&A.csv`.

## RAG Quality Evaluation

Phase 2 includes a lightweight evaluation harness for retrieval and answer quality. Add or edit JSONL cases in:

```text
docs/evaluation_dataset.jsonl
```

Each case can define:

- `question`
- `expected_terms`
- `expected_sources`
- `filters`

Run:

```bash
python scripts/evaluate_rag.py --dataset docs/evaluation_dataset.jsonl
```

To generate a larger retrieval benchmark from retained chunks:

```bash
python scripts/build_retrieval_benchmark.py --output docs/retrieval_benchmark_200.jsonl --limit 200 --text-count 110 --visual-count 50 --table-count 20 --negative-count 20
python scripts/evaluate_rag.py --dataset docs/retrieval_benchmark_200.jsonl --collection dental_docs_clean --retrieval-only --json
```

For machine-readable output:

```bash
python scripts/evaluate_rag.py --json
```

For fast smoke tuning, filter by case type:

```bash
python scripts/evaluate_rag.py --dataset docs/retrieval_benchmark_200.jsonl --collection dental_docs_clean --retrieval-only --case-type text --max-cases 20 --json
python scripts/evaluate_rag.py --dataset docs/retrieval_benchmark_200.jsonl --collection dental_docs_clean --retrieval-only --case-type visual --max-cases 10 --json
python scripts/evaluate_rag.py --dataset docs/retrieval_benchmark_200.jsonl --collection dental_docs_clean --retrieval-only --case-type table_chart --max-cases 10 --json
python scripts/evaluate_rag.py --dataset docs/retrieval_benchmark_200.jsonl --collection dental_docs_clean --retrieval-only --case-type negative_no_visual --max-cases 10 --json
```

The generated benchmark is categorized into text retrieval, visual retrieval, table/chart retrieval, and negative no-visual cases. The evaluator reports pass rate, expected-term recall, top-5 relevance, citation accuracy, visual relevance, and answer faithfulness. Failed cases are written to `cleanup_reports/retrieval_benchmark_failures.jsonl` with query rewrites, top retrieved chunks, reranker/BM25/vector scores, selected visuals, and final citations. Use this after uploading approved dental PDFs to compare retrieval changes.

## API Overview

Auth:

- `POST /api/auth/register`
- `POST /api/auth/login`

Chat:

- `POST /api/chat`
- `GET /api/chat/sessions`
- `POST /api/chat/documents`
- `GET /api/chat/documents/{document_id}`
- `POST /api/feedback`

Admin:

- `GET /api/admin/documents`
- `POST /api/admin/documents`
- `POST /api/admin/documents/{document_id}/reingest`
- `DELETE /api/admin/documents/{document_id}`
- `GET /api/admin/documents/{document_id}/logs`
- `POST /api/admin/dataset/generate`
- `GET /api/admin/dataset/download`

Health:

- `GET /api/health`
- `GET /api/disclaimer`

## Data Model

- `users`: account, password hash, role, active state.
- `documents`: uploaded PDFs and ingestion status.
- `document_chunks`: chunk text, page number, chunk index, Qdrant point ID.
- `chat_sessions`: user-owned conversations.
- `messages`: user and assistant turns, assistant citations as JSON.
- `feedback`: rating and optional comments for assistant messages.

## Tests

```bash
pytest
```

Tests mock external RAG and ingestion calls where needed, so they do not require OpenAI or Qdrant.

## Security Notes

- Never commit `.env`.
- `JWT_SECRET_KEY` must be long and random outside local demos.
- Passwords are stored with bcrypt hashing.
- Admin-only routes enforce role checks.
- Disable `ALLOW_ADMIN_REGISTRATION` after bootstrap.
- Do not expose admin registration in the public UI. Use `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` to seed the admin account.
- This MVP is not HIPAA-ready. Add compliance controls before handling real patient data.

## Project Structure

```text
app/
  core/          configuration, database, security
  routers/       auth, chat, admin, health APIs
  services/      RAG, ingestion, upload storage, dataset generation, web search
  main.py        FastAPI application
frontend/        React/Next.js frontend
static/          legacy FastAPI-served fallback page
tests/           pytest suite
knowledge_base/  optional offline PDFs
uploaded_docs/   runtime admin uploads
docs/            developer notes and roadmap
```

## Remaining Roadmap

- Alembic migrations instead of `create_all`.
- Rate limiting and stronger audit log retention.
- Larger expert-reviewed evaluation dataset for dental factuality and citation quality.
- PHI redaction, consent flows, retention policies, and deployment hardening.
- Streaming chat responses.
- Multi-tenant clinic support.
