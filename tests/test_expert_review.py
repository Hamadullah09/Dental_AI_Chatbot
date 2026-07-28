"""Tests for the human expert review workflow (Phase 8, docs/adr/0016-...): a domain
expert sampling real conversations against a faithfulness/safety/citation-accuracy
rubric, distinct from the user-submitted Feedback queue (tests/test_feedback_review.py).
"""

from app.core.database import SessionLocal
from app.models import ChatSession, ExpertReview, Message, MessageRole, User
from tests.conftest import create_admin_user, register_user


def _insert_conversation(user_id: str, question_text: str) -> str:
    """Inserts a session + user/assistant message pair directly, matching exactly what
    app/routers/chat.py leaves behind (session, user message, assistant message with
    sources_json) - going through the real chat endpoint would require a working LLM.
    Returns the assistant message id."""
    import json
    import uuid

    with SessionLocal() as db:
        session = ChatSession(id=str(uuid.uuid4()), user_id=user_id, title=question_text[:80])
        db.add(session)
        db.commit()

        db.add(Message(id=str(uuid.uuid4()), session_id=session.id, role=MessageRole.user, content=question_text))
        db.commit()

        assistant_id = str(uuid.uuid4())
        db.add(
            Message(
                id=assistant_id,
                session_id=session.id,
                role=MessageRole.assistant,
                content="A cavity is a hole caused by tooth decay.",
                sources_json=json.dumps({"sources": [{"document_name": "Textbook"}], "visuals": [], "answer_mode": "rag_grounded"}),
            )
        )
        db.commit()
        return assistant_id


def _user_id(client, email: str) -> str:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).first().id


def test_sample_returns_unreviewed_conversations_with_question_and_answer(client):
    patient = register_user(client, "reviewsample@example.com")
    user_id = _user_id(client, "reviewsample@example.com")
    message_id = _insert_conversation(user_id, "What is a cavity?")

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    response = client.get("/api/admin/reviews/sample", headers=headers)
    assert response.status_code == 200
    items = response.json()
    match = next((i for i in items if i["message_id"] == message_id), None)
    assert match is not None
    assert match["question"] == "What is a cavity?"
    assert "hole caused by tooth decay" in match["answer"]
    assert match["answer_mode"] == "rag_grounded"
    assert match["sources"] == [{"document_name": "Textbook"}]


def test_submitting_a_review_removes_it_from_the_sample_queue(client):
    user_id = _user_id_or_register(client, "reviewsubmit@example.com")
    message_id = _insert_conversation(user_id, "Why do gums bleed?")

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    before = client.get("/api/admin/reviews/sample", headers=headers).json()
    assert any(i["message_id"] == message_id for i in before)

    submit = client.post(
        f"/api/admin/reviews/{message_id}",
        headers=headers,
        json={"faithfulness": "faithful", "safety": "safe", "citation_accuracy": "accurate", "notes": "Solid answer"},
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["faithfulness"] == "faithful"
    assert body["message_id"] == message_id

    after = client.get("/api/admin/reviews/sample", headers=headers).json()
    assert not any(i["message_id"] == message_id for i in after)

    with SessionLocal() as db:
        review = db.query(ExpertReview).filter(ExpertReview.message_id == message_id).first()
        assert review.safety == "safe"


def test_resubmitting_a_review_updates_the_same_row_not_a_new_one(client):
    user_id = _user_id_or_register(client, "reviewupdate@example.com")
    message_id = _insert_conversation(user_id, "What causes bad breath?")

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    client.post(
        f"/api/admin/reviews/{message_id}",
        headers=headers,
        json={"faithfulness": "unfaithful", "safety": "concerning", "citation_accuracy": "inaccurate"},
    )
    client.post(
        f"/api/admin/reviews/{message_id}",
        headers=headers,
        json={"faithfulness": "faithful", "safety": "safe", "citation_accuracy": "accurate", "notes": "Revised after re-reading"},
    )

    with SessionLocal() as db:
        rows = db.query(ExpertReview).filter(ExpertReview.message_id == message_id).all()
        assert len(rows) == 1
        assert rows[0].faithfulness == "faithful"
        assert rows[0].notes == "Revised after re-reading"


def test_review_rejects_a_rating_outside_the_fixed_vocabulary(client):
    user_id = _user_id_or_register(client, "reviewinvalid@example.com")
    message_id = _insert_conversation(user_id, "What is plaque?")

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    response = client.post(
        f"/api/admin/reviews/{message_id}",
        headers=headers,
        json={"faithfulness": "sort_of", "safety": "safe", "citation_accuracy": "accurate"},
    )
    assert response.status_code == 422


def test_summary_reports_counts_and_percentages(client):
    user_id = _user_id_or_register(client, "reviewsummary@example.com")
    message_id_1 = _insert_conversation(user_id, "Q1")
    message_id_2 = _insert_conversation(user_id, "Q2")

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    client.post(f"/api/admin/reviews/{message_id_1}", headers=headers, json={"faithfulness": "faithful", "safety": "safe", "citation_accuracy": "accurate"})
    client.post(f"/api/admin/reviews/{message_id_2}", headers=headers, json={"faithfulness": "unfaithful", "safety": "safe", "citation_accuracy": "inaccurate"})

    response = client.get("/api/admin/reviews/summary", headers=headers)
    assert response.status_code == 200
    summary = response.json()
    assert summary["total_reviewed"] == 2
    assert summary["safe_pct"] == 100.0
    assert summary["faithful_pct"] == 50.0
    assert summary["by_faithfulness"]["faithful"] == 1
    assert summary["by_faithfulness"]["unfaithful"] == 1


def test_reviews_endpoints_require_admin(client):
    patient = register_user(client, "reviewnonadmin@example.com")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}

    assert client.get("/api/admin/reviews/sample", headers=headers).status_code == 403
    assert client.get("/api/admin/reviews/summary", headers=headers).status_code == 403


def _user_id_or_register(client, email: str) -> str:
    register_user(client, email)
    return _user_id(client, email)
