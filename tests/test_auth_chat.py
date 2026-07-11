from app.schemas import SourceCitation
from tests.conftest import register_user


def test_register_and_login(client):
    payload = register_user(client, "patient@example.com")
    assert payload["access_token"]
    assert payload["user"]["role"] == "patient"

    response = client.post(
        "/api/auth/login",
        json={"email": "patient@example.com", "password": "strong-password"},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_chat_saves_history_and_sources(client, monkeypatch):
    auth = register_user(client, "student@example.com", "student")

    class FakeRAGService:
        def answer(self, question, top_k=None, filters=None):
            return (
                "Brush twice daily with fluoride toothpaste.",
                [
                    SourceCitation(
                        document_id="doc-1",
                        document_name="Dental Guide.pdf",
                        page_number=12,
                        chunk_index=3,
                        score=0.91,
                    )
                ],
            )

    monkeypatch.setattr("app.routers.chat.RAGService", FakeRAGService)

    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        json={"question": "How often should patients brush?"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sources"][0]["document_name"] == "Dental Guide.pdf"
    assert data["sources"][0]["page_number"] == 12
    assert data["answer_mode"] == "rag_grounded"
    assert data["disclaimer"]

    sessions = client.get(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert sessions.status_code == 200
    assert len(sessions.json()[0]["messages"]) == 2

    feedback = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        json={"message_id": data["message_id"], "rating": 5, "comment": "Useful"},
    )
    assert feedback.status_code == 200
