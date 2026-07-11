# Independent OpenAI Backup Endpoint

Use this as a separate serverless deployment for Expo or demos. It should not run on the same machine as the primary Dental AI backend.

Frontend setting:

```bash
NEXT_PUBLIC_BACKUP_OPENAI_ENDPOINT=https://your-backup-domain.example/api/openai-fallback
```

Serverless environment:

```bash
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
ALLOWED_ORIGIN=https://demo.wtechx.tech
```

Expected request:

```json
{
  "question": "What is tooth decay?",
  "session_id": "optional-session-id"
}
```

Expected response shape matches the main app:

```json
{
  "answer": "General dental guidance...",
  "session_id": "",
  "message_id": "openai-backup-...",
  "sources": [],
  "answer_mode": "openai_backup",
  "disclaimer": "..."
}
```
