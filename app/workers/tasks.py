from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Document, DocumentStatus
from app.services.ingestion import IngestionService

logger = logging.getLogger(__name__)


async def ingest_document_task(ctx: dict[str, Any], document_id: str) -> dict[str, str]:
    settings = get_settings()
    logger.info(f"Starting background ingestion for document {document_id}")

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            logger.warning(f"Document {document_id} not found, skipping ingestion")
            return {"status": "not_found"}

        try:
            document.status = DocumentStatus.processing
            db.commit()

            IngestionService().ingest_document(db, document)

            logger.info(f"Document {document_id} ingested successfully")
            return {"status": "completed", "document_id": document_id}

        except Exception as exc:
            logger.error(f"Ingestion failed for document {document_id}: {exc}")
            try:
                document.status = DocumentStatus.failed
                document.error_message = str(exc)[:500]
                db.commit()
            except Exception:
                db.rollback()
            return {"status": "failed", "error": str(exc)}


async def cleanup_expired_tokens(ctx: dict[str, Any]) -> dict[str, str]:
    from datetime import datetime, timezone
    from app.models import RefreshToken

    with SessionLocal() as db:
        expired = db.query(RefreshToken).filter(
            RefreshToken.expires_at < datetime.now(timezone.utc),
            RefreshToken.revoked == False,
        ).count()

        db.query(RefreshToken).filter(
            RefreshToken.expires_at < datetime.now(timezone.utc),
        ).delete()
        db.commit()

        logger.info(f"Cleaned up {expired} expired refresh tokens")
        return {"cleaned": expired}


async def cleanup_old_audit_logs(ctx: dict[str, Any]) -> dict[str, str]:
    from datetime import datetime, timedelta, timezone
    from app.models import AuditLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    with SessionLocal() as db:
        deleted = db.query(AuditLog).filter(AuditLog.created_at < cutoff).delete()
        db.commit()
        logger.info(f"Cleaned up {deleted} old audit logs")
        return {"deleted": deleted}


async def generate_dataset_task(ctx: dict[str, Any], **kwargs: Any) -> dict[str, str]:
    from app.services.dataset_generation import generate_dataset_background

    logger.info("Starting background dataset generation")
    try:
        generate_dataset_background(**kwargs)
        return {"status": "completed"}
    except Exception as exc:
        logger.error(f"Dataset generation failed: {exc}")
        return {"status": "failed", "error": str(exc)}


class WorkerSettings:
    functions = [
        ingest_document_task,
        cleanup_expired_tokens,
        cleanup_old_audit_logs,
        generate_dataset_task,
    ]
    queues = ["default"]
    max_jobs = 4
    job_timeout = 3600
    retry_delay = 5
    max_tries = 3
    health_check_interval = 10

    @classmethod
    def redis_settings(cls) -> Any:
        settings = get_settings()
        from redis import asyncio as aioredis
        return aioredis.from_url(settings.redis_url, decode_responses=True)
