from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging, get_logger
from app.core.redis import close_redis
from app.middleware.metrics import PrometheusMiddleware, metrics_endpoint
from app.middleware.request import RequestIDMiddleware, SecurityHeadersMiddleware, UserContextMiddleware
from app.routers import admin, auth, chat, health
from app.services.users import seed_admin_user


settings = get_settings()

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.extracted_visuals_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as db:
        seed_admin_user(db, settings)
    logger.info("Application started", extra={"extra_data": {"environment": settings.environment}})
    yield
    close_redis()
    logger.info("Application shutdown")


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(UserContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)

if settings.prometheus_enabled:
    app.add_middleware(PrometheusMiddleware)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)

if settings.prometheus_enabled:
    from fastapi import APIRouter
    metrics_router = APIRouter(tags=["metrics"])
    metrics_router.add_api_route(
        settings.prometheus_path,
        endpoint=metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )
    app.include_router(metrics_router)

settings.extracted_visuals_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "ok",
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
    }
