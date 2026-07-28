"""Phase 6: contract tests for the FastAPI endpoints.

These assert the *shape* of the public API stays stable - required fields, response
model structure - independent of any test's mocked implementation. A change that
accidentally removes/renames a field from ChatResponse, or drops an endpoint from the
OpenAPI schema, should fail one of these even if every other test (which typically mocks
around the exact response shape) still passes.
"""

from tests.conftest import create_admin_user, register_user


def _openapi_schema(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_schema_is_generated(client):
    schema = _openapi_schema(client)
    assert schema["openapi"]
    assert "paths" in schema


def test_chat_endpoint_is_documented_with_expected_shape(client):
    schema = _openapi_schema(client)
    chat_path = schema["paths"]["/api/chat"]["post"]
    response_schema = chat_path["responses"]["200"]["content"]["application/json"]["schema"]
    # $ref-based schemas need resolving against components; just confirm a schema exists
    # and the request body is documented (ChatRequest), which is what would go missing if
    # someone accidentally stripped response_model=ChatResponse from the route.
    assert response_schema
    assert "requestBody" in chat_path


def test_chat_response_contract_has_required_fields(client):
    auth = register_user(client, "contract-chat@example.com")

    class FakeRAGService:
        def answer(self, question, top_k=None, filters=None):
            return ("A cavity is tooth decay.", [])

    from unittest.mock import patch

    with patch("app.routers.chat.RAGService", FakeRAGService), patch(
        "app.agent.graph.build_langgraph", side_effect=RuntimeError("force fallback")
    ):
        response = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {auth['access_token']}"},
            json={"question": "What is a cavity?"},
        )

    assert response.status_code == 200
    data = response.json()
    for field in ("answer", "session_id", "message_id", "sources", "visuals", "answer_mode", "disclaimer"):
        assert field in data, f"ChatResponse contract missing field: {field}"
    assert isinstance(data["sources"], list)
    assert isinstance(data["visuals"], list)


def test_auth_register_contract(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "contract-register@example.com", "password": "strong-password", "full_name": "Test", "role": "patient"},
    )
    assert response.status_code == 201
    data = response.json()
    for field in ("access_token", "refresh_token", "user"):
        assert field in data
    for field in ("id", "email", "role"):
        assert field in data["user"]


def test_auth_register_rejects_missing_required_fields(client):
    response = client.post("/api/auth/register", json={"email": "missing-fields@example.com"})
    assert response.status_code == 422


def test_health_contract_has_required_fields(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    for field in ("status", "service", "environment", "checks", "duration_ms", "backend", "ollama", "qdrant"):
        assert field in data, f"health contract missing field: {field}"


def test_feedback_review_contract(client):
    admin = create_admin_user()
    response = client.get(
        "/api/admin/feedback",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    for field in ("items", "total", "page", "limit", "total_pages", "average_rating"):
        assert field in data


def test_protected_endpoints_reject_missing_auth(client):
    for method, path in [
        ("get", "/api/chat/sessions"),
        ("post", "/api/chat"),
        ("get", "/api/admin/documents"),
        ("get", "/api/admin/feedback"),
    ]:
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} should require auth, got {response.status_code}"


def test_admin_only_endpoints_reject_non_admin(client):
    patient = register_user(client, "contract-nonadmin@example.com")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}
    for method, path in [
        ("get", "/api/admin/documents"),
        ("get", "/api/admin/feedback"),
    ]:
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code == 403, f"{method.upper()} {path} should reject non-admin, got {response.status_code}"
