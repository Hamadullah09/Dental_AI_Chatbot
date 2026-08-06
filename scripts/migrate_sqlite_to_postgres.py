"""One-time migration: copy Document/DocumentChunk rows from a source
SQLite export into this environment's configured database (Postgres in
production, via the app's normal DATABASE_URL).

Skips DocumentVisual rows - those reference image files on disk that
aren't part of this migration. Existing rows (matched by primary key)
are left untouched, so this is safe to re-run.

Run inside the api container so it picks up the container's DATABASE_URL:
    docker compose -f docker-compose.dev.yml exec -T api \\
        python scripts/migrate_sqlite_to_postgres.py --source /tmp/dental_ai_export.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import Document, DocumentChunk  # noqa: E402


def copy_row(source_obj, model_cls, overrides: dict | None = None):
    data = {column.name: getattr(source_obj, column.name) for column in model_cls.__table__.columns}
    if overrides:
        data.update(overrides)
    return model_cls(**data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to the source SQLite file")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    source_engine = create_engine(f"sqlite:///{args.source}")
    source_session_factory = sessionmaker(bind=source_engine)
    source_db = source_session_factory()

    init_db()
    target_db = SessionLocal()

    try:
        existing_doc_ids = {row.id for row in target_db.query(Document.id).all()}
        source_docs = source_db.query(Document).order_by(Document.created_at.asc()).all()

        copied_docs = 0
        skipped_docs = 0
        for doc in source_docs:
            if doc.id in existing_doc_ids:
                skipped_docs += 1
                continue
            # uploaded_by references a user id that won't exist in this
            # database - null it out rather than violate the FK.
            target_db.add(copy_row(doc, Document, overrides={"uploaded_by": None}))
            copied_docs += 1
        target_db.commit()
        print(f"Documents: copied={copied_docs} skipped_existing={skipped_docs}")

        existing_chunk_ids = {row.id for row in target_db.query(DocumentChunk.id).all()}
        source_chunks = source_db.query(DocumentChunk).all()

        copied_chunks = 0
        batch = []
        for chunk in source_chunks:
            if chunk.id in existing_chunk_ids:
                continue
            batch.append(copy_row(chunk, DocumentChunk))
            copied_chunks += 1
            if len(batch) >= args.batch_size:
                target_db.add_all(batch)
                target_db.commit()
                batch = []
        if batch:
            target_db.add_all(batch)
            target_db.commit()
        print(f"Document chunks: copied={copied_chunks}")

    finally:
        target_db.close()
        source_db.close()


if __name__ == "__main__":
    main()
