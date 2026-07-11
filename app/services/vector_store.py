from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

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


def collection_exists(qdrant: QdrantClient, collection_name: str) -> bool:
    if hasattr(qdrant, "collection_exists"):
        try:
            return bool(qdrant.collection_exists(collection_name=collection_name))
        except Exception:
            pass
    try:
        qdrant.get_collection(collection_name=collection_name)
        return True
    except Exception:
        return False


def ensure_qdrant_collection(
    qdrant: QdrantClient,
    collection_name: str,
    vector_size: int,
    *,
    replace_if_wrong_size: bool = False,
) -> None:
    exists = collection_exists(qdrant, collection_name)
    if exists:
        if not replace_if_wrong_size:
            return
        try:
            info = qdrant.get_collection(collection_name=collection_name)
            vectors = info.config.params.vectors
            current_size = int(getattr(vectors, "size", 0) or 0)
            if current_size == int(vector_size):
                return
        except Exception:
            pass
        qdrant.recreate_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )
        return

    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )
