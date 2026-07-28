from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Document, DocumentStatus
from app.services.ingestion import IngestionService

if TYPE_CHECKING:
    from arq.connections import RedisSettings

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


async def sync_dentists_task(ctx: dict[str, Any], force: bool = False) -> dict[str, Any]:
    from app.services.scraper.sync_service import DentistSyncService

    logger.info("Starting background dentist sync (force=%s)", force)
    with SessionLocal() as db:
        try:
            service = DentistSyncService(db)
            result = service.sync(force=force)
            logger.info(
                "Dentist sync complete: added=%d updated=%d errors=%d",
                result.added, result.updated, len(result.errors),
            )
            return {
                "status": "completed",
                "added": result.added,
                "updated": result.updated,
                "unchanged": result.unchanged,
                "images_downloaded": result.images_downloaded,
                "errors": result.errors,
                "elapsed_seconds": result.elapsed_seconds,
            }
        except Exception as exc:
            logger.error("Dentist sync failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


async def reindex_dentists_task(ctx: dict[str, Any]) -> dict[str, Any]:
    from app.services.scraper.embedding_service import DentistEmbeddingService

    logger.info("Starting dentist reindex")
    with SessionLocal() as db:
        try:
            service = DentistEmbeddingService(db)
            result = service.reindex()
            logger.info("Dentist reindex complete: %s", result)
            return {"status": "completed", **result}
        except Exception as exc:
            logger.error("Dentist reindex failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


def _build_redis_settings(*, fast_fail: bool = False) -> "RedisSettings":
    from arq.connections import RedisSettings

    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    if fast_fail:
        # Used only when enqueuing from the API request path, where a slow/unresolvable
        # Redis host must not hang the request (arq's defaults - conn_timeout=1,
        # conn_retries=5 - can add up to several seconds, made worse on Windows where a
        # bogus/unresolvable hostname's DNS lookup itself is slow; see
        # docs/GAP_AUDIT_PHASE0.md's Ollama/host.docker.internal finding for the same
        # underlying OS behavior). The long-running worker process (WorkerSettings below)
        # keeps arq's normal retry behavior, since it should keep trying to reconnect.
        redis_settings.conn_timeout = 1
        redis_settings.conn_retries = 1
        redis_settings.conn_retry_delay = 0
    return redis_settings


class WorkerSettings:
    """Run with: arq app.workers.tasks.WorkerSettings

    Phase 4: this module already existed with real task implementations
    (ingest_document_task, cleanup jobs, dataset generation, dentist sync) but was never
    actually wired up - nothing anywhere enqueued a job, and redis_settings returned an
    already-connected aioredis client instead of the arq.connections.RedisSettings object
    arq's worker bootstrap expects, which would have broken `arq worker ...` immediately
    on the first real attempt to run it. See enqueue_ingestion_job() below for the
    FastAPI-side half of actually using this."""

    functions = [
        ingest_document_task,
        cleanup_expired_tokens,
        cleanup_old_audit_logs,
        generate_dataset_task,
        sync_dentists_task,
        reindex_dentists_task,
    ]
    queues = ["default"]
    max_jobs = 4
    job_timeout = 3600
    retry_delay = 5
    max_tries = 3
    health_check_interval = 10
    redis_settings = _build_redis_settings()


async def enqueue_ingestion_job(document_id: str) -> bool:
    """Enqueues document ingestion on the arq worker instead of running it in the API
    process's background-task thread pool, so a large upload's chunking/embedding work
    doesn't compete with request-serving for CPU (Phase 4). Returns False if the queue
    couldn't be reached (Redis down, no worker running) so the caller can fall back to
    running the same task in-process rather than losing the ingestion request.

    Hard-bounded with asyncio.wait_for on top of fast_fail's already-short arq-level
    retry settings: an unresolvable/unreachable Redis host must not hang the upload
    request for more than ~2s before falling back - a real bug caught by this project's
    own test suite hanging on a bogus 'redis' hostname outside its docker network."""
    try:
        from arq import create_pool

        pool = await asyncio.wait_for(create_pool(_build_redis_settings(fast_fail=True)), timeout=2.0)
        try:
            await pool.enqueue_job("ingest_document_task", document_id)
        finally:
            await pool.close()
        return True
    except Exception as exc:
        logger.warning(f"enqueue_ingestion_job.failed document_id={document_id} error={exc}")
        return False


def start_ingestion(document_id: str, *, inline_fallback: Any = None) -> None:
    """Single entry point for both upload routers (app/routers/chat.py,
    app/routers/admin.py): try to enqueue on the arq worker; if that's unreachable, fall
    back to running ingestion in-process.

    `inline_fallback`, if given, is a zero-arg callable the router provides (wrapping its
    own `background_tasks.add_task(ingest_document_background, document_id)` call) - it's
    a parameter rather than always calling ingest_document_task directly so that each
    router's existing test suite, which monkeypatches ITS OWN module-level IngestionService
    import (e.g. app.routers.chat.IngestionService), keeps working. This module's own
    ingest_document_task imports IngestionService from app.services.ingestion directly and
    would silently bypass that mock, running against a real (un-mocked) IngestionService
    instead - the same class of bug documented in docs/GAP_AUDIT_PHASE0.md finding #1."""
    try:
        enqueued = asyncio.run(enqueue_ingestion_job(document_id))
    except Exception:
        enqueued = False
    if enqueued:
        return

    logger.info(f"start_ingestion.queue_unavailable_running_inline document_id={document_id}")
    if inline_fallback is not None:
        inline_fallback()
    else:
        asyncio.run(ingest_document_task({}, document_id))
