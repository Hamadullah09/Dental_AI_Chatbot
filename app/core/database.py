from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


settings = get_settings()
is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 60} if is_sqlite else {}
engine_kwargs = {"poolclass": NullPool} if is_sqlite else {"pool_pre_ping": True}
engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _connection_record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        if "already exists" not in str(exc):
            raise
    ensure_lightweight_columns()


def ensure_lightweight_columns() -> None:
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    document_additions = {
        "title": "VARCHAR(500)",
        "canonical_title": "VARCHAR(500)",
        "author": "VARCHAR(500)",
        "author_or_source": "VARCHAR(500)",
        "publisher": "VARCHAR(500)",
        "edition": "VARCHAR(255)",
        "publication_year": "INTEGER",
        "document_type": "VARCHAR(17) DEFAULT 'textbook' NOT NULL",
        "trust_level": "VARCHAR(6) DEFAULT 'high' NOT NULL",
        "review_status": "VARCHAR(10) DEFAULT 'approved' NOT NULL",
        "specialty": "VARCHAR(255)",
        "dental_specialty": "VARCHAR(255)",
        "topic": "VARCHAR(255)",
        "difficulty_level": "VARCHAR(100)",
        "language": "VARCHAR(100)",
        "file_hash": "VARCHAR(64)",
        "duplicate_group_id": "VARCHAR(100)",
        "content_hash": "VARCHAR(64)",
        "extraction_method": "VARCHAR(100)",
        "ingestion_progress": "INTEGER DEFAULT 0 NOT NULL",
        "ingestion_step": "VARCHAR(255)",
        "ocr_used": "BOOLEAN DEFAULT 0 NOT NULL",
        "ingestion_started_at": "DATETIME",
        "ingestion_completed_at": "DATETIME",
    }
    chunk_columns = {column["name"] for column in inspector.get_columns("document_chunks")} if "document_chunks" in inspector.get_table_names() else set()
    chunk_additions = {
        "quality_score": "FLOAT DEFAULT 1.0 NOT NULL",
        "is_noisy": "BOOLEAN DEFAULT 0 NOT NULL",
        "noise_reasons": "TEXT",
        "canonical_document_title": "VARCHAR(500)",
        "section_title": "VARCHAR(500)",
        "chapter_title": "VARCHAR(500)",
        "dental_specialty": "VARCHAR(255)",
        "topic": "VARCHAR(255)",
        "difficulty_level": "VARCHAR(100)",
        "language": "VARCHAR(100)",
        "trust_level": "VARCHAR(20)",
        "review_status": "VARCHAR(30)",
        "content_hash": "VARCHAR(64)",
    }
    chat_session_columns = {column["name"] for column in inspector.get_columns("chat_sessions")} if "chat_sessions" in inspector.get_table_names() else set()
    chat_session_additions = {
        "archived": "BOOLEAN DEFAULT 0 NOT NULL",
    }
    with engine.begin() as connection:
        for name, ddl_type in document_additions.items():
            if name not in document_columns:
                connection.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {ddl_type}"))
        for name, ddl_type in chunk_additions.items():
            if name not in chunk_columns:
                connection.execute(text(f"ALTER TABLE document_chunks ADD COLUMN {name} {ddl_type}"))
        for name, ddl_type in chat_session_additions.items():
            if name not in chat_session_columns:
                connection.execute(text(f"ALTER TABLE chat_sessions ADD COLUMN {name} {ddl_type}"))
        connection.execute(text("UPDATE documents SET title = original_filename WHERE title IS NULL OR title = ''"))
        connection.execute(text("UPDATE documents SET language = 'English' WHERE language IS NULL OR language = ''"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS document_visuals (
                    id VARCHAR(36) PRIMARY KEY,
                    visual_id VARCHAR(64) UNIQUE NOT NULL,
                    document_id VARCHAR(36) NOT NULL,
                    document_name VARCHAR(500) NOT NULL,
                    page_number INTEGER,
                    visual_type VARCHAR(40) DEFAULT 'unknown' NOT NULL,
                    image_path VARCHAR(1000) NOT NULL,
                    caption_text TEXT,
                    nearby_text TEXT,
                    generated_description TEXT,
                    related_chunk_ids TEXT,
                    quality_score FLOAT DEFAULT 1.0 NOT NULL,
                    review_status VARCHAR(30) DEFAULT 'reviewed' NOT NULL,
                    content_hash VARCHAR(64),
                    qdrant_point_id VARCHAR(64) UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
                """
            )
        )
