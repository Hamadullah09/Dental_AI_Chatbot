from __future__ import annotations

import json
import hashlib
from typing import Any, Optional

import redis
from app.core.config import get_settings


_pool: redis.ConnectionPool | None = None
_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _pool, _client
    if _client is not None:
        return _client
    settings = get_settings()
    _pool = redis.ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )
    _client = redis.Redis(connection_pool=_pool)
    return _client


def close_redis() -> None:
    global _pool, _client
    if _client:
        _client.close()
        _client = None
    if _pool:
        _pool.disconnect()
        _pool = None


class RedisCache:
    def __init__(self, prefix: str = "cache", ttl: int | None = None) -> None:
        self.settings = get_settings()
        self.prefix = prefix
        self.ttl = ttl or self.settings.redis_cache_ttl_seconds

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Any | None:
        try:
            client = get_redis()
            raw = client.get(self._key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except (redis.RedisError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        try:
            client = get_redis()
            serialized = json.dumps(value, default=str)
            client.setex(self._key(key), ttl or self.ttl, serialized)
            return True
        except (redis.RedisError, TypeError):
            return False

    def delete(self, key: str) -> bool:
        try:
            client = get_redis()
            return bool(client.delete(self._key(key)))
        except redis.RedisError:
            return False

    def delete_pattern(self, pattern: str) -> int:
        try:
            client = get_redis()
            full_pattern = self._key(pattern)
            keys = list(client.scan_iter(match=full_pattern, count=100))
            if keys:
                return client.delete(*keys)
            return 0
        except redis.RedisError:
            return 0

    def hash_key(self, *parts: str) -> str:
        combined = "|".join(str(p) for p in parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:32]


class RateLimiter:
    def __init__(self, prefix: str = "ratelimit") -> None:
        self.prefix = prefix

    def _key(self, identifier: str, window: str) -> str:
        return f"{self.prefix}:{identifier}:{window}"

    def is_rate_limited(self, identifier: str, limit: int, window_seconds: int = 60) -> bool:
        try:
            client = get_redis()
            key = self._key(identifier, str(window_seconds))
            current = client.incr(key)
            if current == 1:
                client.expire(key, window_seconds)
            return current > limit
        except redis.RedisError:
            return False

    def get_remaining(self, identifier: str, limit: int, window_seconds: int = 60) -> int:
        try:
            client = get_redis()
            key = self._key(identifier, str(window_seconds))
            current = client.get(key)
            if current is None:
                return limit
            return max(0, limit - int(current))
        except redis.RedisError:
            return limit
