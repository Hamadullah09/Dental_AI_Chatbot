from __future__ import annotations

import time

from app.core.config import get_settings
from app.core.redis import RedisCache


def _jti_cache() -> RedisCache:
    return RedisCache(prefix="revoked_jti")


def _user_cutoff_cache() -> RedisCache:
    return RedisCache(prefix="user_token_cutoff")


def revoke_access_token(jti: str | None, ttl_seconds: int) -> None:
    """Blocklist a single access token by its jti until it would have expired anyway."""
    if not jti:
        return
    _jti_cache().set(jti, True, ttl=max(1, ttl_seconds))


def is_access_token_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    return bool(_jti_cache().get(jti))


def revoke_all_tokens_for_user(user_id: str) -> None:
    """Invalidates every access token issued for this user before now - used for an
    admin-triggered 'sign out everywhere' on a compromised account, without needing to
    track every individual jti ever issued to them."""
    settings = get_settings()
    ttl = settings.access_token_expire_minutes * 60 + 60
    _user_cutoff_cache().set(user_id, time.time(), ttl=ttl)


def is_before_user_cutoff(user_id: str, issued_at: float | None) -> bool:
    if issued_at is None:
        return False
    cutoff = _user_cutoff_cache().get(user_id)
    if cutoff is None:
        return False
    return issued_at < float(cutoff)


def _device_binding_cache() -> RedisCache:
    return RedisCache(prefix="refresh_token_device")


def _device_fingerprint(user_agent: str | None) -> str:
    import hashlib

    return hashlib.sha256((user_agent or "").encode("utf-8")).hexdigest()[:32]


def bind_refresh_token_to_device(token_hash: str, user_agent: str | None, ttl_seconds: int) -> None:
    _device_binding_cache().set(token_hash, _device_fingerprint(user_agent), ttl=max(1, ttl_seconds))


def refresh_token_device_mismatch(token_hash: str, user_agent: str | None) -> bool:
    """Soft device-binding check (Phase 2): compares the current request's device
    fingerprint against the one recorded when this refresh token was issued.

    Deliberately non-blocking - returns True (mismatch) so the caller can log/audit it,
    but does not itself reject the request. User-agent alone changes too often (browser
    updates, app updates) for hard-blocking to be safe without a real false-positive rate
    review; whether to escalate this to blocking or step-up auth is a product policy
    decision, not one this function makes."""
    stored = _device_binding_cache().get(token_hash)
    if stored is None:
        return False
    return bool(stored != _device_fingerprint(user_agent))
