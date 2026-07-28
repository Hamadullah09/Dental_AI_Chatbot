import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import ChatSession, Message, MessageRole, User, UserRole, UserSettings
from app.workers.tasks import WorkerSettings, enforce_chat_retention_task, start_ingestion


def test_worker_settings_redis_settings_is_a_real_settings_object():
    """Regression test: this used to be an already-connected aioredis client instance
    instead of the arq.connections.RedisSettings object arq's worker bootstrap expects -
    would have broken `arq worker app.workers.tasks.WorkerSettings` on first real use."""
    from arq.connections import RedisSettings

    assert isinstance(WorkerSettings.redis_settings, RedisSettings)


def test_start_ingestion_falls_back_when_queue_unavailable(monkeypatch):
    """The autouse no_real_task_queue fixture in conftest.py already forces this path for
    every test; this test asserts the fallback behavior explicitly rather than relying on
    that as an implicit side effect."""
    calls = []

    async def _unavailable(document_id: str) -> bool:
        return False

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _unavailable)

    start_ingestion("doc-123", inline_fallback=lambda: calls.append("fallback_ran"))

    assert calls == ["fallback_ran"]


def test_start_ingestion_skips_fallback_when_enqueued(monkeypatch):
    calls = []

    async def _available(document_id: str) -> bool:
        return True

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _available)

    start_ingestion("doc-456", inline_fallback=lambda: calls.append("fallback_ran"))

    assert calls == []


def test_start_ingestion_uses_default_inline_task_without_fallback_arg(monkeypatch):
    """When called without inline_fallback (no caller-specific mock to route through),
    it should run ingest_document_task directly rather than silently doing nothing."""
    ran_with = {}

    async def _unavailable(document_id: str) -> bool:
        return False

    async def _fake_task(ctx, document_id):
        ran_with["document_id"] = document_id
        return {"status": "completed"}

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _unavailable)
    monkeypatch.setattr("app.workers.tasks.ingest_document_task", _fake_task)

    start_ingestion("doc-789")

    assert ran_with["document_id"] == "doc-789"


def _make_user(db, *, email: str) -> User:
    user = User(id=str(uuid.uuid4()), email=email, hashed_password=hash_password("x"), role=UserRole.patient)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_session_at(db, *, user_id: str, age_days: int) -> str:
    session_id = str(uuid.uuid4())
    session = ChatSession(id=session_id, user_id=user_id, title="old chat")
    db.add(session)
    db.commit()
    db.add(Message(id=str(uuid.uuid4()), session_id=session_id, role=MessageRole.user, content="hi"))
    db.commit()
    # updated_at has onupdate=func.now(); an explicit Core-level UPDATE (not an ORM
    # attribute assignment + commit) is what actually lands a manufactured past
    # timestamp instead of being immediately overwritten back to "now".
    when = datetime.now(timezone.utc) - timedelta(days=age_days)
    db.execute(update(ChatSession).where(ChatSession.id == session_id).values(updated_at=when))
    db.commit()
    return session_id


@pytest.mark.asyncio
async def test_enforce_chat_retention_deletes_sessions_past_custom_window():
    """Regression test for docs/PRODUCT_BENCHMARK.md finding #4: a user who picked a
    30-day retention window in Settings had that value silently ignored - nothing ever
    deleted anything. A session older than the user's own chosen window must be gone
    (messages cascade with it); a session inside the window must survive untouched."""
    with SessionLocal() as db:
        user = _make_user(db, email=f"retention-{uuid.uuid4()}@example.com")
        db.add(UserSettings(id=str(uuid.uuid4()), user_id=user.id, chat_history_retention_days=30))
        db.commit()

        old_session_id = _make_session_at(db, user_id=user.id, age_days=45)
        recent_session_id = _make_session_at(db, user_id=user.id, age_days=5)

    result = await enforce_chat_retention_task({})
    assert result["deleted_sessions"] >= 1

    with SessionLocal() as db:
        assert db.get(ChatSession, old_session_id) is None
        assert (
            db.query(Message).filter(Message.session_id == old_session_id).count() == 0
        ), "messages must cascade-delete with their session"
        assert db.get(ChatSession, recent_session_id) is not None


@pytest.mark.asyncio
async def test_enforce_chat_retention_uses_90_day_default_without_settings_row():
    """A user who has never opened /settings has no UserSettings row (it's only created
    lazily on first GET/PATCH). That must default to 90 days, same as the model column's
    own default, not "keep forever" and not "delete everything.\""""
    with SessionLocal() as db:
        user = _make_user(db, email=f"retention-nodefault-{uuid.uuid4()}@example.com")
        old_session_id = _make_session_at(db, user_id=user.id, age_days=120)
        recent_session_id = _make_session_at(db, user_id=user.id, age_days=10)

    await enforce_chat_retention_task({})

    with SessionLocal() as db:
        assert db.get(ChatSession, old_session_id) is None
        assert db.get(ChatSession, recent_session_id) is not None
