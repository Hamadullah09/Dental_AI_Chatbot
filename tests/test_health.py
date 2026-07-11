def test_health_is_lightweight_and_checks_ollama(client, monkeypatch):
    def fail_if_rag_is_created(*args, **kwargs):
        raise AssertionError("health must not create RAGService, query Qdrant, or run inference")

    monkeypatch.setattr("app.routers.chat.RAGService", fail_if_rag_is_created)
    monkeypatch.setattr(
        "app.routers.health.check_ollama_reachable",
        lambda base_url, timeout_seconds=0.8: {"status": "ok", "status_code": 200},
    )

    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["backend"] == "ok"
    assert data["ollama"]["status"] == "ok"
    assert "duration_ms" in data


def test_health_does_not_fail_when_ollama_is_unreachable(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.health.check_ollama_reachable",
        lambda base_url, timeout_seconds=0.8: {"status": "unreachable", "error": "ConnectError"},
    )

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ollama"]["status"] == "unreachable"
