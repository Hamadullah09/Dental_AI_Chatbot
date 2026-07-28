from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import Text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from cryptography.fernet import Fernet

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_fernet() -> "Fernet":
    """Derives a Fernet key from settings.field_encryption_key (or, if unset, falls back
    to jwt_secret_key so encryption is on by default rather than silently absent - see
    docs/GAP_AUDIT_PHASE0.md Phase 2 PHI section).

    Production should set a dedicated FIELD_ENCRYPTION_KEY sourced from a real secrets
    manager/KMS, not reuse the JWT signing key or rely on this fallback - that's a
    deliberate policy/infra decision left to ops, flagged rather than made silently here.
    """
    from cryptography.fernet import Fernet

    settings = get_settings()
    key_material = settings.field_encryption_key or settings.jwt_secret_key
    if not settings.field_encryption_key:
        logger.warning(
            "encryption.no_dedicated_key_configured "
            "FIELD_ENCRYPTION_KEY is not set; deriving from JWT_SECRET_KEY as a fallback. "
            "Set a dedicated key (ideally from a secrets manager) for production PHI storage."
        )
    derived = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode("utf-8")).digest())
    return Fernet(derived)


class EncryptedText(TypeDecorator[str]):
    """Transparent application-level encryption for PHI text columns (Phase 2).

    Encrypts on write, decrypts on read. Existing plaintext rows (written before this
    column started encrypting) are detected by a failed Fernet decrypt and returned as-is
    rather than raising - this gives a gradual migration path without requiring a
    blocking data-migration script; see scripts/encrypt_existing_phi.py for an optional
    one-time backfill that re-encrypts legacy plaintext rows.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        encrypted: bytes = _get_fernet().encrypt(value.encode("utf-8"))
        return encrypted.decode("ascii")

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        try:
            decrypted: bytes = _get_fernet().decrypt(value.encode("ascii"))
            return decrypted.decode("utf-8")
        except Exception:
            # Not a valid Fernet token - assume legacy plaintext written before encryption
            # was enabled on this column, rather than raising and breaking every read.
            return value
