from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models import ChatSession, Message, MessageRole, User, UserMemory

logger = get_logger(__name__)


class MemoryService:
    def get_or_create_memory(self, db: Session, user_id: str) -> UserMemory:
        memory = db.query(UserMemory).filter(UserMemory.user_id == user_id).first()
        if not memory:
            memory = UserMemory(user_id=user_id)
            db.add(memory)
            db.commit()
            db.refresh(memory)
        return memory

    def update_memory(
        self,
        user_id: str,
        *,
        preferred_language: str | None = None,
        simplify_for_patient: bool | None = None,
        preferred_specialty: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            memory = self.get_or_create_memory(db, user_id)
            if preferred_language is not None:
                memory.preferred_language = preferred_language
            if simplify_for_patient is not None:
                memory.simplify_for_patient = simplify_for_patient
            if preferred_specialty is not None:
                memory.preferred_specialty = preferred_specialty
            memory.last_interaction_at = datetime.now(timezone.utc)
            db.commit()

    def _extract_topics(self, question: str) -> list[str]:
        topic_keywords = {
            "caries": ["cavity", "decay", "caries", "filling", "restoration"],
            "periodontal": ["gum", "periodontal", "gingivitis", "periodontitis", "bleeding"],
            "endodontic": ["root canal", "pulp", "endodontic", "nerve"],
            "orthodontic": ["braces", "orthodontic", "aligner", "malocclusion", "crowding"],
            "surgery": ["extraction", "surgery", "implant", "wisdom tooth", "oral surgery"],
            "prosthodontic": ["crown", "bridge", "denture", "prosthesis", "veneer"],
            "oral_pathology": ["lesion", "ulcer", "oral cancer", "leukoplakia", "lichen planus"],
            "pediatric": ["child", "pediatric", "baby tooth", "children"],
            "cosmetic": ["whitening", "cosmetic", "aesthetic", "veneers", "smile"],
        }
        q = question.lower()
        topics = []
        for topic, keywords in topic_keywords.items():
            if any(kw in q for kw in keywords):
                topics.append(topic)
        return topics

    def track_topic(self, user_id: str, question: str) -> None:
        topics = self._extract_topics(question)
        if not topics:
            return
        with SessionLocal() as db:
            memory = self.get_or_create_memory(db, user_id)
            existing = json.loads(memory.frequently_asked_topics or "{}")
            for topic in topics:
                existing[topic] = existing.get(topic, 0) + 1
            memory.frequently_asked_topics = json.dumps(existing)
            db.commit()

    def get_memory_context(self, user_id: str, db: Session | None = None) -> dict[str, Any]:
        context: dict[str, Any] = {
            "preferences": {},
            "recent_topics": [],
            "recent_sessions": [],
        }

        if db is None:
            with SessionLocal() as local_db:
                return self._load_memory_context(local_db, user_id)
        return self._load_memory_context(db, user_id)

    def _load_memory_context(self, db: Session, user_id: str) -> dict[str, Any]:
        memory = db.query(UserMemory).filter(UserMemory.user_id == user_id).first()
        if memory:
            context: dict[str, Any] = {
                "preferences": {
                    "preferred_language": memory.preferred_language,
                    "simplify_for_patient": memory.simplify_for_patient,
                    "preferred_specialty": memory.preferred_specialty or "",
                },
                "recent_topics": list(json.loads(memory.frequently_asked_topics or "{}").keys())[:5],
            }
        else:
            context = {"preferences": {}, "recent_topics": []}

        recent_sessions = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(5)
            .all()
        )

        session_summaries = []
        seen_titles = set()
        for session in recent_sessions:
            if session.title and session.title not in seen_titles:
                seen_titles.add(session.title)
                session_summaries.append({
                    "title": session.title[:100],
                    "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                })

        context["recent_sessions"] = session_summaries
        return context

    def format_memory_for_prompt(self, user_id: str) -> str:
        context = self.get_memory_context(user_id)
        parts = []

        prefs = context.get("preferences", {})
        if prefs.get("simplify_for_patient"):
            parts.append("User prefers simplified, patient-friendly explanations.")
        if prefs.get("preferred_language") and prefs["preferred_language"] != "en":
            parts.append(f"User prefers responses in {prefs['preferred_language']}.")
        if prefs.get("preferred_specialty"):
            parts.append(f"User is interested in {prefs['preferred_specialty']} dentistry.")

        topics = context.get("recent_topics", [])
        if topics:
            parts.append(f"User has previously asked about: {', '.join(topics)}.")

        sessions = context.get("recent_sessions", [])
        if sessions:
            titles = [s["title"] for s in sessions if s.get("title")]
            if titles:
                parts.append(f"Recent conversations: {' | '.join(titles[:3])}.")

        return "\n".join(parts)
