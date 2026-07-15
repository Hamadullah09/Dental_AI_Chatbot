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
| `LLMService` | `app/services/llm.py` | Ollama/OpenAI integration |
| `ModelRouter` | `app/services/model_router.py` | Multi-provider LLM routing |
| `IngestionService` | `app/services/ingestion.py` | PDF parsing, chunking, embedding |
| `VisualPipeline` | `app/services/visual_pipeline.py` | Image OCR and classification |
| `CrossEncoderReranker` | `app/services/cross_encoder.py` | BGE reranking |
| `MemoryManager` | `app/agent/nodes/memory.py` | Short/long-term memory |
| `SecurityManager` | `app/services/security.py` | Input sanitization, backups |
| `EvaluationPipeline` | `app/services/evaluation.py` | RAG quality metrics |

### Data Models (PostgreSQL)

| Table | Purpose |
|-------|---------|
| `users` | User accounts with roles (admin/dentist/hygienist/patient) |
| `documents` | Uploaded PDFs with metadata |
| `document_chunks` | Extracted text chunks |
| `document_visuals` | Extracted images/diagrams |
| `chat_sessions` | Chat conversation sessions |
| `messages` | Individual messages |
| `feedback` | User feedback on answers |
| `refresh_tokens` | JWT refresh tokens |
| `audit_logs` | Security audit trail |
| `conversation_memory` | Long-term conversation memory |

### Vector Database (Qdrant)

Collections:
- `dental_chunks` - Text chunk embeddings (all-MiniLM-L6-v2)
- `dental_visuals` - Visual embeddings

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

1. **Authentication**: JWT access tokens (24h) + refresh tokens (7d)
2. **Authorization**: Role-based (admin, dentist, hygienist, patient)
3. **Rate Limiting**: Per-IP throttling via Redis
4. **Input Sanitization**: XSS/injection prevention
5. **Security Headers**: CSP, HSTS, X-Frame-Options
6. **Audit Logging**: All actions tracked
7. **Encrypted Backups**: Fernet encryption for database backups
8. **IP Allowlisting**: Optional IP restriction

## Monitoring

- **Prometheus**: Request count, latency, LLM performance, retrieval metrics
- **Grafana**: Real-time dashboards
- **Structured Logging**: JSON logs with request IDs
- **OpenTelemetry**: Distributed tracing (optional)

## Deployment

See `docs/DEPLOYMENT.md` for detailed deployment instructions.
