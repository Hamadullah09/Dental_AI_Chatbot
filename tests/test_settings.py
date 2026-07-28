"""Tests for GET/PATCH /settings - previously zero coverage. Added alongside the
chat-history-retention fix (docs/PRODUCT_BENCHMARK.md finding #4), which also caught the
frontend settings page (frontend/app/settings/page.tsx) sending several field names the
backend schema didn't have at all (push_notifications, data_sharing_consent,
hipaa_consent, chat_history_retention_days) - silently dropped by Pydantic on every save.
"""

from tests.conftest import register_user


def test_get_settings_creates_defaults_on_first_access(client):
    auth = register_user(client, "settings-defaults@example.com")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    response = client.get("/api/settings", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["chat_history_retention_days"] == 90
    assert data["hipaa_consent"] is False
    assert data["push_notifications"] is True


def test_patch_settings_persists_previously_dropped_fields(client):
    auth = register_user(client, "settings-persist@example.com")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    response = client.patch(
        "/api/settings",
        headers=headers,
        json={
            "chat_history_retention_days": 30,
            "push_notifications": False,
            "data_sharing_consent": True,
            "hipaa_consent": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["chat_history_retention_days"] == 30
    assert data["push_notifications"] is False
    assert data["data_sharing_consent"] is True
    assert data["hipaa_consent"] is True

    # Persisted, not just echoed back from the request - a fresh GET must agree.
    refetched = client.get("/api/settings", headers=headers).json()
    assert refetched["chat_history_retention_days"] == 30
    assert refetched["hipaa_consent"] is True


def test_patch_settings_rejects_retention_value_outside_the_offered_options(client):
    auth = register_user(client, "settings-invalid-retention@example.com")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    response = client.patch(
        "/api/settings",
        headers=headers,
        json={"chat_history_retention_days": 45},
    )

    assert response.status_code == 422
