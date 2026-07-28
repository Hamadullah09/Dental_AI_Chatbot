from app.workers.tasks import WorkerSettings, start_ingestion


def test_worker_settings_redis_settings_is_a_real_settings_object():
    """Regression test: this used to be an already-connected aioredis client instance
    instead of the arq.connections.RedisSettings object arq's worker bootstrap expects -
    would have broken `arq worker app.workers.tasks.WorkerSettings` on first real use."""
    from arq.connections import RedisSettings

    assert isinstance(WorkerSettings.redis_settings, RedisSettings)


def test_start_ingestion_falls_back_when_queue_unavailable(monkeypatch):
    """The autouse no_real_task_queue fixture in conftest.py already forces this path for
    every test; this test asserts the fallback behavior explicitly rather than relying on
    that as an implicit side effect."""
    calls = []

    async def _unavailable(document_id: str) -> bool:
        return False

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _unavailable)

    start_ingestion("doc-123", inline_fallback=lambda: calls.append("fallback_ran"))

    assert calls == ["fallback_ran"]


def test_start_ingestion_skips_fallback_when_enqueued(monkeypatch):
    calls = []

    async def _available(document_id: str) -> bool:
        return True

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _available)

    start_ingestion("doc-456", inline_fallback=lambda: calls.append("fallback_ran"))

    assert calls == []


def test_start_ingestion_uses_default_inline_task_without_fallback_arg(monkeypatch):
    """When called without inline_fallback (no caller-specific mock to route through),
    it should run ingest_document_task directly rather than silently doing nothing."""
    ran_with = {}

    async def _unavailable(document_id: str) -> bool:
        return False

    async def _fake_task(ctx, document_id):
        ran_with["document_id"] = document_id
        return {"status": "completed"}

    monkeypatch.setattr("app.workers.tasks.enqueue_ingestion_job", _unavailable)
    monkeypatch.setattr("app.workers.tasks.ingest_document_task", _fake_task)

    start_ingestion("doc-789")

    assert ran_with["document_id"] == "doc-789"
