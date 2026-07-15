import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.middleware.metrics import CHAT_QUERIES, ACTIVE_INGESTIONS


router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    started = time.perf_counter()
    settings = get_settings()
    checks: dict[str, Any] = {}

    checks["database"] = check_database(db)
    checks["qdrant"] = check_qdrant(settings.qdrant_url, settings.qdrant_timeout_seconds)
    checks["ollama"] = check_ollama_reachable(settings.ollama_base_url)
    checks["redis"] = check_redis()

    all_ok = all(c.get("status") == "ok" for c in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": settings.app_name,
        "environment": settings.environment,
        "checks": checks,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    checks = {
        "database": check_database(db),
        "qdrant": check_qdrant(settings.qdrant_url, settings.qdrant_timeout_seconds),
        "redis": check_redis(),
    }
    ready = all(c.get("status") == "ok" for c in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}


@router.get("/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/disclaimer")
def disclaimer() -> dict[str, str]:
    return {"disclaimer": get_settings().medical_disclaimer}


def check_database(db: Session) -> dict[str, Any]:
    try:
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "duration_ms": duration_ms}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def check_qdrant(base_url: str | None, timeout: int = 5) -> dict[str, Any]:
    if not base_url:
        return {"status": "not_configured"}
    try:
        start = time.perf_counter()
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base_url.rstrip('/')}/collections")
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if response.is_success:
            data = response.json()
            collections = data.get("result", {}).get("collections", [])
            return {"status": "ok", "collections": len(collections), "duration_ms": duration_ms}
        return {"status": "error", "status_code": response.status_code}
    except httpx.HTTPError as exc:
        return {"status": "unreachable", "error": exc.__class__.__name__}


def check_ollama_reachable(base_url: str | None, timeout_seconds: float = 2.0) -> dict[str, Any]:
    if not base_url:
        return {"status": "not_configured"}
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(f"{base_url.rstrip('/')}/api/tags")
        payload = response.json() if response.is_success else {}
        model_names = {str(model.get("name") or model.get("model") or "") for model in payload.get("models", [])}
        settings = get_settings()
        return {
            "status": "ok" if response.is_success else "error",
            "status_code": response.status_code,
            "text_model": settings.ollama_model,
            "text_model_available": settings.ollama_model in model_names if model_names else None,
            "vision_model": settings.ollama_vision_model,
            "vision_model_available": settings.ollama_vision_model in model_names if model_names else None,
        }
    except httpx.HTTPError as exc:
        return {"status": "unreachable", "error": exc.__class__.__name__}


def check_redis() -> dict[str, Any]:
    try:
        client = get_redis()
        start = time.perf_counter()
        client.ping()
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        info = client.info("memory")
        return {
            "status": "ok",
            "duration_ms": duration_ms,
            "used_memory_human": info.get("used_memory_human", "unknown"),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
