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

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    db_path = ROOT / "test_dental_ai.db"
    if db_path.exists():
        db_path.unlink()


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
