import time
from typing import Any

import httpx
from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    started = time.perf_counter()
    settings = get_settings()
    ollama = check_ollama_reachable(settings.ollama_base_url)
    return {
        "status": "ok",
        "service": settings.app_name,
        "backend": "ok",
        "ollama": ollama,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@router.get("/disclaimer")
def disclaimer() -> dict[str, str]:
    return {"disclaimer": get_settings().medical_disclaimer}


def check_ollama_reachable(base_url: str | None, timeout_seconds: float = 0.8) -> dict[str, Any]:
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
        return {
            "status": "unreachable",
            "error": exc.__class__.__name__,
        }
