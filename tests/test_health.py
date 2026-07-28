def test_health_is_lightweight_and_checks_ollama(client, monkeypatch):
    def fail_if_rag_is_created(*args, **kwargs):
        raise AssertionError("health must not create RAGService, query Qdrant, or run inference")

    monkeypatch.setattr("app.routers.chat.RAGService", fail_if_rag_is_created)
    monkeypatch.setattr(
        "app.routers.health.check_ollama_reachable",
        lambda base_url, timeout_seconds=0.8: {"status": "ok", "status_code": 200},
    )
    # Qdrant has no live service in this test environment (same as real CI, which runs no
    # Qdrant container) - mock it too so this test verifies the ollama-check plumbing and
    # "no live inference" contract it's named for, instead of accidentally depending on a
    # reachable Qdrant instance.
    monkeypatch.setattr(
        "app.routers.health.check_qdrant",
        lambda base_url, timeout=3: {"status": "ok", "collections": 0},
    )
    monkeypatch.setattr(
        "app.routers.health.check_redis",
        lambda: {"status": "ok", "duration_ms": 1.0, "used_memory_human": "1M"},
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
    data = response.json()
    assert data["ollama"]["status"] == "unreachable"
    # An unreachable Ollama must be reported, but must not crash the endpoint or hide the
    # per-check detail behind a generic 500 (Phase 1: explicit fallback, not silent failure).
    assert data["status"] == "degraded"
