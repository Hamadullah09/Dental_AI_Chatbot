# Dental AI Chatbot - Troubleshooting Guide

## Common Issues

### 1. Docker Services Won't Start

**Symptom**: `docker-compose up` fails or services exit immediately

**Solutions**:
```bash
# Check Docker is running
docker info

# Check port availability
netstat -ano | findstr :8000
netstat -ano | findstr :3000
netstat -ano | findstr :5432

# Remove old containers
docker-compose down
docker system prune -f

# Rebuild images
docker-compose build --no-cache
docker-compose up -d
```

### 2. Database Connection Failed

**Symptom**: API logs show `connection refused` or `authentication failed`

**Solutions**:
```bash
# Check PostgreSQL is running
docker-compose logs postgres

# Verify credentials match .env
grep DATABASE_URL .env
grep POSTGRES_PASSWORD .env

# Test connection
docker-compose exec postgres psql -U dental -d dental_ai -c "SELECT 1;"

# Reset database
docker-compose down postgres
docker volume rm dental_ai_chatbot_postgres_data
docker-compose up -d postgres
```

### 3. Qdrant Connection Failed

**Symptom**: `qdrant_client` errors in API logs

**Solutions**:
```bash
# Check Qdrant status
curl http://localhost:6333/healthz

# Check Qdrant logs
docker-compose logs qdrant

# Verify Qdrant is in same Docker network
docker-compose exec api curl http://qdrant:6333/healthz
```

### 4. Ollama Not Responding

**Symptom**: LLM generation fails, timeout errors

**Solutions**:
```bash
# Check Ollama is running
docker-compose logs ollama

# Test Ollama API
curl http://localhost:11434/api/version

# Check GPU access
docker exec -it ollama nvidia-smi

# Verify model is pulled
docker exec -it ollama ollama list

# Pull model if missing
docker exec -it ollama ollama pull qwen2.5-vl:7b
```

### 5. Redis Connection Failed

**Symptom**: Rate limiting not working, caching errors

**Solutions**:
```bash
# Check Redis status
docker-compose logs redis

# Test Redis
docker-compose exec redis redis-cli ping

# Check Redis memory
docker-compose exec redis redis-cli info memory
```

### 6. Frontend Can't Connect to API

**Symptom**: Browser console shows CORS errors or network failures

**Solutions**:
```bash
# Check CORS configuration
grep CORS_ORIGINS .env

# Ensure your domain is included
CORS_ORIGINS=https://yourdomain.com,http://localhost:3000

# Check Nginx proxy
docker-compose logs nginx

# Test API directly
curl http://localhost:8000/api/health
```

### 7. PDF Upload Fails

**Symptom**: Upload returns error or file not processed

**Solutions**:
```bash
# Check upload directory permissions
ls -la uploads/

# Check API logs for ingestion errors
docker-compose logs api | grep -i ingest

# Verify Tesseract is installed
docker-compose exec api tesseract --version

# Check file size (max 50MB default)
ls -lh your_file.pdf
```

### 8. Chat Returns Empty Response

**Symptom**: API responds but answer is empty

**Solutions**:
```bash
# Check Ollama model availability
curl http://localhost:11434/api/tags

# Check if document was ingested
curl http://localhost:8000/api/admin/documents

# Test RAG directly
python -c "
from app.services.rag import RAGService
rag = RAGService()
result = rag.answer('What is dental caries?')
print(result)
"
```

### 9. GPU Not Detected

**Symptom**: Ollama falls back to CPU, slow responses

**Solutions**:
```bash
# Check NVIDIA driver
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Reinstall NVIDIA Container Toolkit
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 10. Slow Response Times

**Symptom**: Chat takes >30 seconds to respond

**Solutions**:
```bash
# Monitor GPU usage
nvidia-smi

# Check Ollama model size
docker exec -it ollama ollama list

# Reduce model size for faster responses
# In .env:
OLLAMA_DEFAULT_MODEL=qwen2.5-vl:7b  # Use smaller model

# Check embedding model
# In .env:
EMBEDDING_DEVICE=cpu  # Or gpu if available
```

## Log Analysis

### API Logs
```bash
# View real-time logs
docker-compose logs -f api

# Search for errors
docker-compose logs api 2>&1 | grep -i error

# Search for specific request
docker-compose logs api 2>&1 | grep "request_id"
```

### Structured Logs
Logs are in JSON format with these fields:
```json
{
  "message": "Chat completed",
  "level": "info",
  "timestamp": "2024-01-01T12:00:00Z",
  "extra_data": {
    "user_id": "uuid",
    "duration_ms": 1234.5,
    "answer_mode": "rag_grounded"
  },
  "request_id": "uuid"
}
```

### Prometheus Metrics
```bash
# Check metrics
curl http://localhost:9090/metrics

# Key metrics:
# - http_requests_total
# - http_request_duration_seconds
# - llm_generation_duration_seconds
# - retrieval_duration_seconds
```

## Health Checks

### API Health
```bash
curl http://localhost:8000/api/health
# Returns: {"status": "healthy", "database": "connected", ...}
```

### Readiness Check
```bash
curl http://localhost:8000/api/ready
# Returns: 200 if ready, 503 if not
```

### Liveness Check
```bash
curl http://localhost:8000/api/live
# Returns: 200 always (unless process is dead)
```

## Performance Issues

### High Memory Usage
```bash
# Check container memory
docker stats

# Reduce Ollama context window
# In .env:
OLLAMA_NUM_CTX=4096  # Default 8192
```

### High CPU Usage
```bash
# Check which service is using CPU
docker stats

# Reduce embedding batch size
# In .env:
EMBEDDING_BATCH_SIZE=32  # Default 64
```

### Database Slow Queries
```bash
# Enable query logging
docker-compose exec postgres psql -U dental -d dental_ai -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
docker-compose restart postgres

# Check slow queries
docker-compose logs postgres | grep "duration"
```

## Recovery Procedures

### Database Corruption
```bash
# Stop services
docker-compose stop api

# Restore from backup
cat backup_20240101.sql | docker-compose exec -T postgres psql -U dental dental_ai

# Restart services
docker-compose start api
```

### Qdrant Data Loss
```bash
# Re-ingest all documents
python -c "
from app.services.ingestion import IngestionService
from app.core.database import SessionLocal
from app.models import Document

with SessionLocal() as db:
    docs = db.query(Document).all()
    for doc in docs:
        IngestionService().ingest_document(db, doc)
"
```

### Complete Reset
```bash
# Stop all services
docker-compose down

# Remove all data
docker volume rm dental_ai_chatbot_postgres_data
docker volume rm dental_ai_chatbot_qdrant_data
docker volume rm dental_ai_chatbot_redis_data

# Start fresh
docker-compose up -d

# Re-create admin user
python -c "
from app.services.users import seed_admin_user
from app.core.database import SessionLocal
from app.core.config import get_settings

settings = get_settings()
with SessionLocal() as db:
    seed_admin_user(db, settings)
"
```

## Getting Help

1. Check logs first: `docker-compose logs -f`
2. Run health checks: `curl http://localhost:8000/api/health`
3. Check Docker status: `docker-compose ps`
4. Review environment: `cat .env`
5. Check GitHub issues: https://github.com/Hamadullah09/Dental_AI_Chatbot/issues
