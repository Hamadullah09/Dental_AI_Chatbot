from tests.conftest import create_admin_user, register_user


def _post_chat_and_feedback(client, auth, question, rating, comment=None):
    from unittest.mock import patch

    class FakeRAGService:
        def answer(self, question, top_k=None, filters=None):
            return (f"Answer to: {question}", [])

    with patch("app.routers.chat.RAGService", FakeRAGService), patch(
        "app.agent.graph.build_langgraph", side_effect=RuntimeError("force fallback")
    ):
        response = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"question": question},
        )
    assert response.status_code == 200, response.text
    message_id = response.json()["message_id"]

    feedback = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        json={"message_id": message_id, "rating": rating, "comment": comment},
    )
    assert feedback.status_code == 200, feedback.text
    return message_id


def test_admin_can_list_feedback_worst_first(client):
    admin = create_admin_user()
    patient = register_user(client, "feedback-patient@example.com")

    _post_chat_and_feedback(client, patient, "What is a cavity?", rating=5)
    _post_chat_and_feedback(client, patient, "How do I treat gum disease?", rating=1, comment="Answer was wrong")

    response = client.get(
        "/api/admin/feedback",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    # Worst-first ordering
    assert data["items"][0]["rating"] == 1
    assert data["items"][0]["comment"] == "Answer was wrong"
    assert data["items"][0]["question"] == "How do I treat gum disease?"
    assert "Answer to:" in data["items"][0]["answer"]
    assert data["average_rating"] == 3.0


def test_admin_can_filter_feedback_by_max_rating(client):
    admin = create_admin_user()
    patient = register_user(client, "feedback-filter@example.com")

    _post_chat_and_feedback(client, patient, "Q1", rating=5)
    _post_chat_and_feedback(client, patient, "Q2", rating=2)

    response = client.get(
        "/api/admin/feedback",
        params={"max_rating": 3},
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["rating"] == 2


def test_non_admin_cannot_list_feedback(client):
    patient = register_user(client, "feedback-nonadmin@example.com")
    response = client.get(
        "/api/admin/feedback",
        headers={"Authorization": f"Bearer {patient['access_token']}"},
    )
    assert response.status_code == 403
