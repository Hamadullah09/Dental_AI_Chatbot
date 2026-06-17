from tests.conftest import create_admin_user
from app.models import DocumentStatus


def test_admin_can_upload_list_and_delete_document(client, monkeypatch):
    auth = create_admin_user()

    class FakeIngestionService:
        def ingest_document(self, db, document):
            document.status = DocumentStatus.ready
            document.chunk_count = 2
            db.commit()
            return 2

        def delete_document_vectors(self, document_id):
            return None

    monkeypatch.setattr("app.routers.admin.IngestionService", FakeIngestionService)

    response = client.post(
        "/api/admin/documents",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        data={
            "book_title": "Sample Dental Book",
            "author_or_source": "Dental Test Source",
            "year": "2024",
            "document_type": "guideline",
            "trust_level": "high",
            "review_status": "approved",
            "language": "English",
        },
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]
    assert response.json()["status"] == "processing"
    assert response.json()["title"] == "Sample Dental Book"
    assert response.json()["author_or_source"] == "Dental Test Source"
    assert response.json()["publication_year"] == 2024
    assert response.json()["file_hash"]

    listing = client.get(
        "/api/admin/documents",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert listing.status_code == 200
    assert listing.json()[0]["original_filename"] == "sample.pdf"
    assert listing.json()[0]["chunk_count"] == 2
    assert listing.json()[0]["status"] == "ready"

    deleted = client.delete(
        f"/api/admin/documents/{document_id}",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert deleted.status_code == 204
