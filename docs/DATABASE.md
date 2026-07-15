# Dental AI Chatbot - Database Schema

## Overview

PostgreSQL 16 database with SQLAlchemy ORM. Uses Alembic for migrations.

## Tables

### users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'patient',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

**Roles**: `admin`, `dentist`, `hygienist`, `patient`

### documents

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500),
    original_filename VARCHAR(500) NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,
    uploaded_by UUID NOT NULL REFERENCES users(id),
    status VARCHAR(50) NOT NULL DEFAULT 'processing',
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    visual_count INTEGER DEFAULT 0,
    pages_total INTEGER,
    extraction_method VARCHAR(50),
    canonical_title VARCHAR(500),
    author VARCHAR(255),
    specialty VARCHAR(255),
    dental_specialty VARCHAR(255),
    topic VARCHAR(255),
    difficulty_level VARCHAR(50),
    language VARCHAR(50) DEFAULT 'English',
    content_hash VARCHAR(255),
    ocr_used BOOLEAN DEFAULT FALSE,
    ingestion_progress INTEGER DEFAULT 0,
    ingestion_step VARCHAR(100),
    ingestion_started_at TIMESTAMP WITH TIME ZONE,
    ingestion_completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_specialty ON documents(specialty);
```

**Status values**: `processing`, `ready`, `failed`

### document_chunks

```sql
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_number INTEGER,
    section_title VARCHAR(500),
    chapter_title VARCHAR(500),
    chunk_hash VARCHAR(255),
    quality_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_document_chunks_page_number ON document_chunks(page_number);
CREATE UNIQUE INDEX idx_document_chunks_unique ON document_chunks(document_id, chunk_index);
```

### document_visuals

```sql
CREATE TABLE document_visuals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    visual_type VARCHAR(50) NOT NULL,
    image_path VARCHAR(1000),
    image_url VARCHAR(1000),
    caption_text TEXT,
    generated_description TEXT,
    ocr_text TEXT,
    relevance_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_document_visuals_document_id ON document_visuals(document_id);
CREATE INDEX idx_document_visuals_page_number ON document_visuals(page_number);
```

### chat_sessions

```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(500),
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
```

### messages

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

**Role values**: `user`, `assistant`, `system`

### feedback

```sql
CREATE TABLE feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    message_id UUID NOT NULL REFERENCES messages(id),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    feedback_type VARCHAR(50) DEFAULT 'quality',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_feedback_user_id ON feedback(user_id);
CREATE INDEX idx_feedback_message_id ON feedback(message_id);
```

### refresh_tokens

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
```

### audit_logs

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    details TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
```

### user_activities

```sql
CREATE TABLE user_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    activity_type VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_activities_user_id ON user_activities(user_id);
CREATE INDEX idx_user_activities_type ON user_activities(activity_type);
```

### conversation_memory

```sql
CREATE TABLE conversation_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    session_id UUID NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    importance FLOAT DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_conversation_memory_user_id ON conversation_memory(user_id);
CREATE INDEX idx_conversation_memory_session_id ON conversation_memory(session_id);
CREATE INDEX idx_conversation_memory_type ON conversation_memory(memory_type);
```

**Memory types**: `short_term`, `long_term`, `summary`, `preference`

## Relationships

```
users ──┬── documents (uploaded_by)
        ├── chat_sessions (user_id)
        ├── feedback (user_id)
        ├── refresh_tokens (user_id)
        ├── audit_logs (user_id)
        ├── user_activities (user_id)
        └── conversation_memory (user_id)

documents ──┬── document_chunks (document_id)
            └── document_visuals (document_id)

chat_sessions ── messages (session_id)

messages ── feedback (message_id)
```

## Migrations

### Create Migration

```bash
# Auto-generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Migration File Location

```
alembic/versions/
├── 001_initial.py
├── 002_add_refresh_tokens.py
└── ...
```

## Seed Data

### Admin User

```python
# Created automatically on startup
admin = User(
    email=settings.ADMIN_EMAIL,
    full_name=settings.ADMIN_FULL_NAME,
    hashed_password=hash_password(settings.ADMIN_PASSWORD),
    role=UserRole.admin,
    is_active=True,
)
```

## Backup & Restore

### Backup

```bash
# Full database backup
docker-compose exec postgres pg_dump -U dental dental_ai > backup.sql

# Compressed backup
docker-compose exec postgres pg_dump -U dental dental_ai | gzip > backup.sql.gz
```

### Restore

```bash
# Restore from backup
cat backup.sql | docker-compose exec -T postgres psql -U dental dental_ai

# Restore from compressed backup
gunzip -c backup.sql.gz | docker-compose exec -T postgres psql -U dental dental_ai
```

### Encrypted Backup

```python
from app.services.security import SecurityManager

sm = SecurityManager()
sm.backup_database()  # Creates encrypted backup in ./backups/
```

## Performance Tuning

### Indexes

All foreign keys and frequently queried columns are indexed.

### Connection Pool

```python
# app/core/config.py
DB_POOL_SIZE=20      # Base connections
DB_MAX_OVERFLOW=10   # Additional connections
DB_POOL_TIMEOUT=30   # Timeout in seconds
```

### Query Optimization

```python
# Use selectinload for relationships
documents = db.query(Document).options(
    selectinload(Document.chunks),
    selectinload(Document.visuals)
).all()
```

## Schema Evolution

1. Make changes to models in `app/models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review generated migration
4. Apply: `alembic upgrade head`
5. Test application
