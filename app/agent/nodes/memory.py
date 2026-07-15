from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)


class MemoryManager:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_short_term_memory(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        try:
            client = get_redis()
            key = f"memory:short:{user_id}:{session_id}"
            raw = client.lrange(key, 0, -1)
            return [json.loads(item) for item in raw]
        except Exception:
            return []

    def add_short_term_memory(self, user_id: str, session_id: str, role: str, content: str) -> None:
        try:
            client = get_redis()
            key = f"memory:short:{user_id}:{session_id}"
            entry = json.dumps({"role": role, "content": content[:500], "timestamp": datetime.now(timezone.utc).isoformat()})
            client.rpush(key, entry)
            client.expire(key, self.settings.redis_session_ttl_seconds)
            client.ltrim(key, -20, -1)
        except Exception as exc:
            logger.warning(f"Failed to add short-term memory: {exc}")

    def get_long_term_memory(self, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        try:
            from app.core.database import SessionLocal
            from app.models import ConversationMemory

            with SessionLocal() as db:
                memories = (
                    db.query(ConversationMemory)
                    .filter(
                        ConversationMemory.user_id == user_id,
                        ConversationMemory.memory_type == "long_term",
                    )
                    .order_by(ConversationMemory.importance_score.desc())
                    .limit(limit)
                    .all()
                )
                return [{"content": m.content, "importance": m.importance_score} for m in memories]
        except Exception as exc:
            logger.warning(f"Failed to get long-term memory: {exc}")
            return []

    def store_long_term_memory(self, user_id: str, content: str, importance: float = 0.5) -> None:
        try:
            from app.core.database import SessionLocal
            from app.models import ConversationMemory
            import uuid

            with SessionLocal() as db:
                memory = ConversationMemory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    memory_type="long_term",
                    content=content[:2000],
                    importance_score=importance,
                )
                db.add(memory)
                db.commit()
        except Exception as exc:
            logger.warning(f"Failed to store long-term memory: {exc}")

    def get_conversation_summary(self, user_id: str, session_id: str) -> str:
        try:
            client = get_redis()
            key = f"memory:summary:{user_id}:{session_id}"
            return client.get(key) or ""
        except Exception:
            return ""

    def store_conversation_summary(self, user_id: str, session_id: str, summary: str) -> None:
        try:
            client = get_redis()
            key = f"memory:summary:{user_id}:{session_id}"
            client.setex(key, self.settings.redis_session_ttl_seconds, summary[:1000])
        except Exception as exc:
            logger.warning(f"Failed to store conversation summary: {exc}")

    def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        try:
            client = get_redis()
            key = f"memory:prefs:{user_id}"
            raw = client.get(key)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def store_user_preference(self, user_id: str, key: str, value: Any) -> None:
        try:
            client = get_redis()
            redis_key = f"memory:prefs:{user_id}"
            prefs = self.get_user_preferences(user_id)
            prefs[key] = value
            client.setex(redis_key, 86400 * 30, json.dumps(prefs, default=str))
        except Exception as exc:
            logger.warning(f"Failed to store user preference: {exc}")

    def build_memory_context(self, user_id: str, session_id: str) -> str:
        parts = []

        short_term = self.get_short_term_memory(user_id, session_id)
        if short_term:
            recent = short_term[-6:]
            history = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:200]}" for m in recent)
            parts.append(f"Recent conversation:\n{history}")

        summary = self.get_conversation_summary(user_id, session_id)
        if summary:
            parts.append(f"Conversation summary:\n{summary}")

        long_term = self.get_long_term_memory(user_id, limit=3)
        if long_term:
            lt_text = "\n".join(f"- {m['content'][:150]}" for m in long_term)
            parts.append(f"User context:\n{lt_text}")

        prefs = self.get_user_preferences(user_id)
        if prefs:
            parts.append(f"User preferences: {json.dumps(prefs)}")

        return "\n\n".join(parts)


memory_manager = MemoryManager()
