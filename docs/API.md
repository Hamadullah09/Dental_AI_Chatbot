# Dental AI Chatbot - API Documentation

## Base URL

```
http://localhost:8000/api
```

## Authentication

All endpoints (except health and auth) require JWT Bearer token:

```bash
Authorization: Bearer <access_token>
```

## Endpoints

### Health

#### GET /health
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "qdrant": "connected",
  "redis": "connected",
  "ollama": "connected"
}
```

#### GET /ready
Readiness check (returns 503 if not ready).

#### GET /live
Liveness check (always returns 200).

---

### Authentication

#### POST /auth/register
Register a new user.

**Request**:
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "full_name": "John Doe",
  "role": "patient"
}
```

**Response** (201):
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "patient"
  }
}
```

#### POST /auth/login
Login with email and password.

**Request**:
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response**:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { ... }
}
```

#### POST /auth/refresh
Refresh access token.

**Request**:
```json
{
  "refresh_token": "eyJ..."
}
```

**Response**:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { ... }
}
```

#### POST /auth/logout
Revoke refresh token.

**Request**:
```json
{
  "refresh_token": "eyJ..."
}
```

#### GET /auth/me
Get current user profile.

**Response**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "dentist",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### Chat

#### POST /chat
Send a chat message (synchronous).

**Request**:
```json
{
  "question": "What is dental caries?",
  "session_id": "uuid" (optional),
  "document_id": "uuid" (optional),
  "search_web": false,
  "top_k": 5,
  "document_types": ["pdf"],
  "trust_levels": ["verified"],
  "review_status": "approved",
  "min_year": 2020
}
```

**Response**:
```json
{
  "answer": "Dental caries, commonly known as cavities...",
  "session_id": "uuid",
  "message_id": "uuid",
  "sources": [
    {
      "source_type": "pdf",
      "document_id": "uuid",
      "document_name": "dental_textbook.pdf",
      "page_number": 45,
      "chunk_index": 12,
      "score": 0.92
    }
  ],
  "visuals": [
    {
      "visual_id": "uuid",
      "document_name": "dental_textbook.pdf",
      "page_number": 46,
      "visual_type": "diagram",
      "caption_text": "Cross-section of tooth showing cavity",
      "score": 0.88
    }
  ],
  "answer_mode": "rag_grounded",
  "disclaimer": "Dental AI is for education..."
}
```

#### POST /chat/stream
Send a chat message (streaming SSE).

**Request**: Same as POST /chat

**Response**: Server-Sent Events stream
```
data: {"type": "content", "text": "Dental"}
data: {"type": "content", "text": " caries"}
data: {"type": "content", "text": " is"}
data: {"type": "sources", "sources": [...], "visuals": [...]}
data: {"type": "metadata", "answer_mode": "rag_grounded"}
data: [DONE]
```

---

### Chat Sessions

#### GET /chat/sessions
Get all chat sessions for current user.

**Query Parameters**:
- `limit`: Number of sessions (default 20)
- `offset`: Offset for pagination

**Response**:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "title": "Question about dental caries",
      "created_at": "2024-01-01T00:00:00Z",
      "message_count": 5
    }
  ],
  "total": 25
}
```

#### GET /chat/sessions/{session_id}
Get a specific chat session with messages.

**Response**:
```json
{
  "session": {
    "id": "uuid",
    "title": "Question about dental caries",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "What is dental caries?",
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "Dental caries, commonly known as cavities...",
      "sources": [...],
      "visuals": [...],
      "created_at": "2024-01-01T00:00:01Z"
    }
  ]
}
```

#### DELETE /chat/sessions/{session_id}
Delete a chat session.

**Response**: 204 No Content

---

### Feedback

#### POST /chat/feedback
Submit feedback on a message.

**Request**:
```json
{
  "message_id": "uuid",
  "rating": 5,
  "comment": "Very helpful answer",
  "feedback_type": "quality"
}
```

**Response** (201):
```json
{
  "id": "uuid",
  "message_id": "uuid",
  "rating": 5,
  "comment": "Very helpful answer",
  "feedback_type": "quality",
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### Documents

#### POST /documents/upload
Upload a PDF document.

**Request**: `multipart/form-data`
- `file`: PDF file (max 50MB)
- `title`: Document title (optional)
- `specialty`: Dental specialty (optional)

**Response** (201):
```json
{
  "id": "uuid",
  "title": "Dental Textbook",
  "original_filename": "dental_textbook.pdf",
  "status": "processing",
  "chunk_count": 0,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### GET /documents
Get all documents for current user.

**Query Parameters**:
- `limit`: Number of documents (default 20)
- `offset`: Offset for pagination
- `status`: Filter by status (processing, ready, failed)

**Response**:
```json
{
  "documents": [
    {
      "id": "uuid",
      "title": "Dental Textbook",
      "original_filename": "dental_textbook.pdf",
      "status": "ready",
      "chunk_count": 150,
      "specialty": "general_dentistry",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 10
}
```

#### GET /documents/{document_id}
Get document details.

**Response**:
```json
{
  "id": "uuid",
  "title": "Dental Textbook",
  "original_filename": "dental_textbook.pdf",
  "status": "ready",
  "chunk_count": 150,
  "visual_count": 25,
  "specialty": "general_dentistry",
  "language": "English",
  "pages_total": 450,
  "ocr_used": false,
  "created_at": "2024-01-01T00:00:00Z",
  "ingestion_started_at": "2024-01-01T00:00:05Z",
  "ingestion_completed_at": "2024-01-01T00:02:30Z"
}
```

#### DELETE /documents/{document_id}
Delete a document and its chunks.

**Response**: 204 No Content

---

### Admin Endpoints

#### GET /admin/documents
Get all documents (admin only).

#### PUT /admin/documents/{document_id}/review
Review/approve a document (admin only).

**Request**:
```json
{
  "review_status": "approved",
  "review_notes": "Looks good"
}
```

#### POST /admin/dataset/generate
Generate training dataset from conversations.

**Request**:
```json
{
  "min_rating": 4,
  "max_samples": 1000,
  "include_feedback": true
}
```

---

### Metrics

#### GET /metrics
Prometheus metrics endpoint (no auth required).

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Question cannot be empty"
}
```

### 401 Unauthorized
```json
{
  "detail": "Invalid email or password"
}
```

### 403 Forbidden
```json
{
  "detail": "Admin accounts are created by system configuration only"
}
```

### 404 Not Found
```json
{
  "detail": "Chat session not found"
}
```

### 409 Conflict
```json
{
  "detail": "Email is already registered"
}
```

### 429 Too Many Requests
```json
{
  "detail": "Too many login attempts. Please try again later."
}
```

### 503 Service Unavailable
```json
{
  "detail": "The dental AI model did not respond in time. Please try again."
}
```

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /auth/login | 10 requests | 60 seconds |
| POST /auth/register | 5 requests | 300 seconds |
| POST /auth/refresh | 20 requests | 60 seconds |
| POST /chat | 20 requests | 60 seconds |
| POST /documents/upload | 5 requests | 60 seconds |

Rate limits are per IP address.
