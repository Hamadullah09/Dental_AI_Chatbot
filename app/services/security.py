from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SecurityManager:
    def __init__(self) -> None:
        self.settings = get_settings()

    def validate_api_key(self, api_key: str, provider: str) -> bool:
        if not api_key:
            return False
        if provider == "openai":
            return api_key.startswith("sk-") and len(api_key) > 20
        if provider == "tavily":
            return len(api_key) > 10
        if provider == "brave":
            return len(api_key) > 10
        return True

    def sanitize_input(self, text: str) -> str:
        import bleach
        cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
        cleaned = cleaned.replace("<script", "").replace("javascript:", "")
        return cleaned[:10000]

    def check_ip_allowlist(self, ip: str) -> bool:
        allowlist = self._get_ip_allowlist()
        if not allowlist:
            return True
        return ip in allowlist

    def _get_ip_allowlist(self) -> list[str]:
        try:
            from app.core.redis import get_redis
            client = get_redis()
            raw = client.get("security:ip_allowlist")
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def log_security_event(self, event_type: str, details: dict[str, Any], ip: str | None = None) -> None:
        logger.warning(f"Security event: {event_type}", extra={"extra_data": {**details, "ip": ip, "timestamp": datetime.now(timezone.utc).isoformat()}})

        try:
            from app.core.redis import get_redis
            client = get_redis()
            event_data = json.dumps({"type": event_type, "details": details, "ip": ip, "timestamp": datetime.now(timezone.utc).isoformat()})
            client.lpush("security:events", event_data)
            client.ltrim("security:events", 0, 999)
        except Exception:
            pass

    def generate_api_key(self, prefix: str = "dai") -> str:
        import secrets
        key = secrets.token_urlsafe(32)
        return f"{prefix}_{key}"

    def hash_api_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    def encrypt_backup(self, data: bytes, password: str) -> bytes:
        from cryptography.fernet import Fernet
        key = hashlib.sha256(password.encode()).digest()
        f = Fernet(key)
        return f.encrypt(data)

    def decrypt_backup(self, encrypted_data: bytes, password: str) -> bytes:
        from cryptography.fernet import Fernet
        key = hashlib.sha256(password.encode()).digest()
        f = Fernet(key)
        return f.decrypt(encrypted_data)


security_manager = SecurityManager()
