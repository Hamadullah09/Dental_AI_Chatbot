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
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
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
        user = User(
            email=email,
            full_name="Admin User",
            hashed_password=hash_password("strong-password"),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
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
