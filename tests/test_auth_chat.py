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
    """Exercises the legacy RAGService fallback path explicitly (by forcing the LangGraph
    build to fail) rather than mocking app.routers.chat.RAGService and hoping the primary
    path uses it - it doesn't. The primary /chat path runs the LangGraph agent, whose nodes
    do `from app.services.rag import RAGService` internally at call time; that resolves
    fresh from app.services.rag and never sees a patch applied only to
    app.routers.chat.RAGService. This mismatch was itself a confirmed gap - see
    docs/GAP_AUDIT_PHASE0.md finding #1/#9 - so this test now forces and asserts the
    fallback explicitly instead of accidentally not testing anything."""
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

    def broken_graph():
        raise RuntimeError("simulated LangGraph build failure")

    monkeypatch.setattr("app.routers.chat.RAGService", FakeRAGService)
    monkeypatch.setattr("app.agent.graph.build_langgraph", broken_graph)

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


def test_agent_graph_fallback_is_logged_and_metered(client, monkeypatch):
    """Regression test for finding #1: a LangGraph failure must not fail open silently -
    it must be logged and counted so the fallback rate is observable (see
    app.routers.chat.chat's AGENT_GRAPH_FALLBACK_TOTAL usage). RAGService is mocked so this
    exercises only the fallback bookkeeping, not real Qdrant/Ollama network calls."""
    from app.middleware.metrics import AGENT_GRAPH_FALLBACK_TOTAL

    auth = register_user(client, "fallback-metric@example.com", "patient")

    class FakeRAGService:
        def answer(self, question, top_k=None, filters=None):
            return ("A cavity is tooth decay.", [])

    def broken_graph():
        raise ValueError("simulated failure for metric test")

    monkeypatch.setattr("app.agent.graph.build_langgraph", broken_graph)
    monkeypatch.setattr("app.routers.chat.RAGService", FakeRAGService)

    before = AGENT_GRAPH_FALLBACK_TOTAL.labels(reason="ValueError")._value.get()

    response = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        json={"question": "What is a cavity?"},
    )

    assert response.status_code == 200, response.text
    after = AGENT_GRAPH_FALLBACK_TOTAL.labels(reason="ValueError")._value.get()
    assert after == before + 1
