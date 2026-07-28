from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
from typing import Any

from jose import JWTError, jwt

from app.core.config import get_settings


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return (
        f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
        "iat": now,
        "type": "access",
        # jti lets a single access token be individually revoked (blocklisted) before its
        # natural expiry - e.g. on logout or an admin-triggered "revoke all sessions".
        "jti": base64.b64encode(os.urandom(16)).decode("ascii"),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
        "type": "refresh",
        "jti": base64.b64encode(os.urandom(16)).decode("ascii"),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return payload
    except JWTError as exc:
        raise ValueError("Invalid authentication token") from exc


def decode_refresh_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
        return payload
    except JWTError as exc:
        raise ValueError("Invalid refresh token") from exc


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_KNOWN_PLACEHOLDER_JWT_SECRETS = {
    "change-me-in-production",
    "dental-ai-secret-key-change-in-production-32chars",
    "",
}
_KNOWN_PLACEHOLDER_ADMIN_PASSWORDS = {"admin123", "changeme", "password", ""}


def assert_no_default_secrets_in_production() -> None:
    """Startup guard (Phase 2): .env.docker and .env.example ship with known placeholder
    secrets so `docker compose up` works out of the box for local development - see
    docs/GAP_AUDIT_PHASE0.md finding #15. If ENVIRONMENT=production is ever combined with
    one of those placeholders still in place, refuse to start rather than run with a
    publicly-known JWT signing key or admin password."""
    settings = get_settings()
    if settings.environment.lower() not in {"production", "prod"}:
        return

    problems = []
    if settings.jwt_secret_key in _KNOWN_PLACEHOLDER_JWT_SECRETS:
        problems.append("JWT_SECRET_KEY is still set to a known placeholder value")
    if settings.admin_password and settings.admin_password in _KNOWN_PLACEHOLDER_ADMIN_PASSWORDS:
        problems.append("ADMIN_PASSWORD is still set to a known placeholder value")

    if problems:
        raise RuntimeError(
            "Refusing to start with ENVIRONMENT=production and insecure default secrets: "
            + "; ".join(problems)
            + ". Set real secrets (ideally from a secrets manager, not a tracked .env file)."
        )
