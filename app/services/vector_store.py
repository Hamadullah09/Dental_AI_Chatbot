from functools import lru_cache

from qdrant_client import QdrantClient

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    if settings.qdrant_local_path:
        return QdrantClient(path=settings.qdrant_local_path)
    if not settings.qdrant_url:
        return QdrantClient(path="qdrant_storage")
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        check_compatibility=False,
    )
