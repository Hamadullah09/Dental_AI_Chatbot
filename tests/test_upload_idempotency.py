from io import BytesIO

from reportlab.pdfgen import canvas

from app.models import DocumentStatus
from tests.conftest import register_user


def tiny_pdf_bytes() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, "Sample idempotency upload.")
    pdf.save()
    return buffer.getvalue()


class FakeIngestionService:
    def ingest_document(self, db, document):
        document.status = DocumentStatus.ready
        document.chunk_count = 1
        db.commit()
        return 1


def test_repeated_upload_with_same_idempotency_key_does_not_duplicate(client, monkeypatch):
    """Phase 1: retried uploads with the same Idempotency-Key must return the same
    document instead of creating (and re-ingesting) a duplicate."""
    monkeypatch.setattr("app.routers.chat.IngestionService", FakeIngestionService)
    auth = register_user(client, "idempotent-upload@example.com")

    headers = {
        "Authorization": f"Bearer {auth['access_token']}",
        "Idempotency-Key": "retry-key-123",
    }

    first = client.post(
        "/api/chat/documents",
        headers=headers,
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = client.post(
        "/api/chat/documents",
        headers=headers,
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first_id

    listing = client.get(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert listing.status_code == 200


def test_upload_without_idempotency_key_creates_separate_documents(client, monkeypatch):
    monkeypatch.setattr("app.routers.chat.IngestionService", FakeIngestionService)
    auth = register_user(client, "no-idempotency-key@example.com")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    first = client.post(
        "/api/chat/documents",
        headers=headers,
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )
    second = client.post(
        "/api/chat/documents",
        headers=headers,
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_different_idempotency_keys_create_separate_documents(client, monkeypatch):
    monkeypatch.setattr("app.routers.chat.IngestionService", FakeIngestionService)
    auth = register_user(client, "different-keys@example.com")

    first = client.post(
        "/api/chat/documents",
        headers={"Authorization": f"Bearer {auth['access_token']}", "Idempotency-Key": "key-a"},
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )
    second = client.post(
        "/api/chat/documents",
        headers={"Authorization": f"Bearer {auth['access_token']}", "Idempotency-Key": "key-b"},
        files={"file": ("sample.pdf", tiny_pdf_bytes(), "application/pdf")},
    )

    assert first.json()["id"] != second.json()["id"]
