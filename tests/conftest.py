import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///./test_dental_ai.db"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["ALLOW_ADMIN_REGISTRATION"] = "true"

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Redis-dependent features (idempotency keys, rate limiting, degraded-answer cache)
    fail open when Redis is unreachable, which is safe for prod but means tests would
    silently verify nothing about their actual caching behavior in an environment with no
    live Redis. fakeredis gives them a real, in-memory Redis to exercise instead - reset
    per test so state never leaks across test cases."""
    import fakeredis

    from app.core import redis as redis_module

    fake_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake_client)
    yield fake_client
    fake_client.flushall()


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    from app.core.resilience import embedding_breaker, ollama_breaker, qdrant_breaker

    ollama_breaker.reset()
    qdrant_breaker.reset()
    embedding_breaker.reset()
    yield
    ollama_breaker.reset()
    qdrant_breaker.reset()
    embedding_breaker.reset()


@pytest.fixture(autouse=True)
def clean_database():
    # Deliberately does NOT call engine.dispose() or delete the sqlite file between
    # tests. SQLite runs in WAL mode (app/core/database.py) which keeps -wal/-shm
    # companion files that Windows can hold a lock on slightly after a connection
    # closes; disposing the engine and unlinking the file per-test raced with that lock
    # intermittently, occasionally leaving the next test with a missing/half-deleted
    # database ("no such table: users") when many tests ran back-to-back. drop_all +
    # create_all alone gives full schema/data isolation between tests without ever
    # touching the file on disk, so the risky dispose+unlink dance isn't needed.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database_file():
    yield
    engine.dispose()
    db_path = ROOT / "test_dental_ai.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except PermissionError:
            pass


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register_user(client: TestClient, email: str, role: str = "patient") -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "strong-password",
            "full_name": "Test User",
            "role": role,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_admin_user(email: str = "admin@example.com") -> dict:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                full_name="Admin User",
                hashed_password=hash_password("strong-password"),
                role=UserRole.admin,
                is_active=True,
            )
            db.add(user)
        else:
            user.role = UserRole.admin
            user.hashed_password = hash_password("strong-password")
            user.is_active = True
        db.commit()
        db.refresh(user)
        token = create_access_token(user.id, {"role": user.role.value})
        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role.value,
            },
        }
