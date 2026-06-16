from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": get_settings().app_name}


@router.get("/disclaimer")
def disclaimer() -> dict[str, str]:
    return {"disclaimer": get_settings().medical_disclaimer}
