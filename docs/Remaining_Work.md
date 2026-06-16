# Remaining Work

The MVP now includes FastAPI services, JWT auth, roles, PostgreSQL-ready models, Qdrant ingestion, admin PDF management, chat history, citations, feedback, Docker Compose, and tests.

## Production Hardening

- Add Alembic migrations and a release migration workflow.
- Move PDF ingestion to a background worker such as Celery, RQ, or FastAPI background tasks with progress tracking.
- Add API rate limiting, structured logging, request IDs, and admin audit logs.
- Add full PHI controls before real patient use: consent, retention policy, encryption review, access logs, and redaction.
- Disable public admin registration after first bootstrap.

## RAG Quality

- Add hybrid retrieval and reranking.
- Add citation verification tests that require every clinical claim to map to a retrieved source.
- Add evaluation datasets for common dental questions.
- Add safety classifiers for emergency, medication, pediatric, pregnancy, and post-operative scenarios.

## Frontend

- Replace the static MVP with a component frontend when product scope stabilizes.
- Add document ingestion progress and richer chat session management.
- Add admin feedback review and export.

## Operations

- Add CI for linting, tests, Docker build, and dependency scanning.
- Add backup/restore documentation for PostgreSQL and Qdrant.
- Add environment-specific deployment guides.
