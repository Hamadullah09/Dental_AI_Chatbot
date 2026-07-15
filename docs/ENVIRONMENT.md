# Dental AI Chatbot - Environment Variables

## Quick Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development` or `production` |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | - | Secret key for JWT tokens |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

## Complete Reference

### Application

```bash
APP_NAME="Dental AI Chatbot"
ENVIRONMENT=development          # development | production
API_PREFIX=/api                  # API path prefix
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Database

```bash
DATABASE_URL=postgresql+psycopg://dental:password@postgres:5432/dental_ai
POSTGRES_PASSWORD=change-this-postgres-password
DB_POOL_SIZE=20                  # Connection pool size
DB_MAX_OVERFLOW=10               # Max overflow connections
DB_POOL_TIMEOUT=30               # Pool timeout seconds
```

### Authentication

```bash
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440     # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS=7
ALLOW_ADMIN_REGISTRATION=false
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-admin-password
ADMIN_FULL_NAME="Dental AI Admin"
```

### Redis

```bash
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=20
REDIS_CACHE_TTL_SECONDS=3600
REDIS_SESSION_TTL_SECONDS=86400
REDIS_RATE_LIMIT_TTL_SECONDS=60
```

### Qdrant

```bash
QDRANT_URL=http://qdrant:6333
QDRANT_LOCAL_PATH=
QDRANT_API_KEY=
QDRANT_TIMEOUT_SECONDS=120
QDRANT_COLLECTION=dental_chunks
```

### Ollama / LLM

```bash
OLLAMA_BASE_URL=http://HOST_IP:11434
OLLAMA_DEFAULT_MODEL=qwen2.5-vl:7b
OLLAMA_VISION_MODEL=qwen2.5-vl:7b
OLLAMA_TEXT_MODEL=qwen3:14b
OLLAMA_EMBEDDING_MODEL=all-minilm-l6-v2
OLLAMA_TIMEOUT=120
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=2048
OLLAMA_NUM_GPU_LAYERS=35
OLLAMA_TEMPERATURE=0.1
OLLAMA_TOP_P=0.9
OLLAMA_TOP_K=40
OLLAMA_REPEAT_PENALTY=1.1
OLLAMA_HEALTH_CHECK_TIMEOUT=5.0
```

### OpenAI (Fallback)

```bash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
OPENAI_TEMPERATURE=0.1
OPENAI_MAX_TOKENS=2048
OPENAI_MODEL_FALLBACKS=gpt-4o-mini,gpt-4o
```

### Embeddings

```bash
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
EMBEDDING_DEVICE=cpu
EMBEDDING_BATCH_SIZE=64
```

### RAG Pipeline

```bash
RETRIEVAL_TOP_K=5
RETRIEVAL_MIN_RELEVANCE_SCORE=0.3
ENABLE_QUERY_REWRITING=true
ENABLE_KEYWORD_SEARCH=true
ENABLE_VISUAL_RETRIEVAL=true
ENABLE_ADJACENT_CHUNK_EXPANSION=true
MULTI_QUERY_MAX_VARIANTS=3
RAG_MODE=corrective              # simple | memory | multi_query | hyde | corrective | self_rag
```

### Visual RAG

```bash
ENABLE_MULTIMODAL_RAG=true
VISUAL_PAGE_SNAPSHOT_ZOOM=1.6
VISUAL_MIN_RELEVANCE_SCORE=0.95
VISUAL_CANDIDATE_MULTIPLIER=4
VISUAL_MAX_TO_ANALYZE=2
VISUAL_OBSERVATION_MAX_WORDS=80
```

### Ingestion

```bash
UPLOAD_DIR=./uploads
EXTRACTED_VISUALS_DIR=./extracted_visuals
CHUNK_SIZE=800
CHUNK_OVERLAP=200
MAX_UPLOAD_SIZE_MB=50
INGESTION_TIMEOUT_SECONDS=600
```

### OCR

```bash
OCR_DPI=250
OCR_LANGUAGE=eng
OCR_CONFIG=--psm 6
OCR_MIN_LINE_LENGTH=4
TESSERACT_CMD=/usr/bin/tesseract
POPPLER_PATH=/usr/bin
```

### Rate Limiting

```bash
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_CHAT_PER_MINUTE=20
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_UPLOAD_PER_MINUTE=5
```

### Streaming

```bash
STREAMING_ENABLED=true
STREAMING_CHUNK_SIZE=10
STREAMING_TIMEOUT_SECONDS=300
```

### Security

```bash
IP_ALLOWLIST=
BACKUP_ENCRYPTION_KEY=
BACKUP_DIR=./backups
BACKUP_RETENTION_DAYS=30
```

### Monitoring

```bash
LOG_LEVEL=INFO                   # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=json                  # json | human
LOG_FILE=
PROMETHEUS_ENABLED=true
PROMETHEUS_PATH=/metrics
```

### Workers (arq)

```bash
WORKER_CONCURRENCY=4
WORKER_MAX_RETRIES=3
WORKER_RETRY_DELAY_SECONDS=5
```

### Medical

```bash
MEDICAL_DISCLAIMER="Dental AI is for education and clinical decision support only. It does not replace diagnosis, treatment planning, or emergency care from a licensed dentist."
```

## Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Generate strong `JWT_SECRET_KEY` (32+ chars)
- [ ] Set strong `POSTGRES_PASSWORD`
- [ ] Set strong `ADMIN_PASSWORD`
- [ ] Configure `CORS_ORIGINS` with your domain
- [ ] Set `OLLAMA_BASE_URL` to office PC IP
- [ ] Set `OLLAMA_NUM_GPU_LAYERS` for your GPU
- [ ] Configure Cloudflare SSL
- [ ] Enable port forwarding
- [ ] Set `PROMETHEUS_ENABLED=true`
- [ ] Configure `LOG_LEVEL=INFO` or `WARNING`
