from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    existing = {column["name"] for column in inspector.get_columns("documents")}
    additions = {
        "title": "VARCHAR(500)",
        "author_or_source": "VARCHAR(500)",
        "edition": "VARCHAR(255)",
        "publication_year": "INTEGER",
        "document_type": "VARCHAR(17) DEFAULT 'textbook' NOT NULL",
        "trust_level": "VARCHAR(6) DEFAULT 'high' NOT NULL",
        "review_status": "VARCHAR(10) DEFAULT 'approved' NOT NULL",
        "specialty": "VARCHAR(255)",
        "language": "VARCHAR(100)",
        "file_hash": "VARCHAR(64)",
    }
    with engine.begin() as connection:
        for name, ddl_type in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {ddl_type}"))
        connection.execute(text("UPDATE documents SET title = original_filename WHERE title IS NULL OR title = ''"))
        connection.execute(text("UPDATE documents SET language = 'English' WHERE language IS NULL OR language = ''"))
