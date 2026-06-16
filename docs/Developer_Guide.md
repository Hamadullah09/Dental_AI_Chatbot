# Developer Guide

## Service Boundaries

- `app/routers`: HTTP concerns, validation, auth dependencies, response models.
- `app/services`: reusable application logic for ingestion, retrieval, generation, and upload storage.
- `app/models.py`: SQLAlchemy persistence models.
- `rag.py` and `ingest.py`: compatibility entry points kept at the repository root.

## Adding A New LLM Provider

Update `RAGService.generate_answer` in `app/services/rag.py`. Keep `retrieve`, `build_prompt`, and citation formatting unchanged so the API contract remains stable.

## Adding A New Document Type

Add a parser that returns `ParsedChunk` records with:

- text
- page or section number
- chunk index

Then call the same Qdrant upsert path used by PDF ingestion.

## Database Migrations

This MVP uses `Base.metadata.create_all` for simple local setup. Production should add Alembic:

```bash
alembic init migrations
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

## Testing Strategy

- Unit test auth and role restrictions with SQLite.
- Mock `RAGService` in API tests to avoid network calls.
- Test parser metadata using generated PDFs.
- Add integration tests against Docker PostgreSQL and Qdrant before production deployment.
