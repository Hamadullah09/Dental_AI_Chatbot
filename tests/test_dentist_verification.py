"""Tests for the dentist account verification workflow (Phase 8).

Regression coverage for docs/PRODUCT_BENCHMARK.md finding #1: registering as "dentist"
used to be rejected outright with a 403 and no way for anyone to ever actually get one -
the registration UI promised "admin verification required" but there was no verifier.
Now registration creates a normal, immediately-usable patient account plus a pending
verification request; only an admin approving it flips the role to dentist.
"""

from app.core.database import SessionLocal
from app.models import User
from tests.conftest import create_admin_user, register_user


def test_register_as_dentist_requires_a_license_number(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "nolicense@example.com", "password": "strong-password", "full_name": "No License", "role": "dentist"},
    )
    assert response.status_code == 422


def test_register_as_dentist_creates_a_usable_patient_account_pending_review(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "pendingdentist@example.com",
            "password": "strong-password",
            "full_name": "Dr. Pending",
            "role": "dentist",
            "license_number": "PMDC-12345",
            "clinic_name": "Smile Clinic",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    # Usable immediately, as a patient, not left with no account at all.
    assert data["user"]["role"] == "patient"
    assert data["user"]["dentist_verification_status"] == "pending"
    assert data["access_token"]

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "pendingdentist@example.com").first()
        assert user.dentist_license_number == "PMDC-12345"
        assert user.dentist_clinic_name == "Smile Clinic"
        assert user.dentist_verification_requested_at is not None


def test_admin_can_list_pending_dentist_requests(client):
    register_user(client, "pending1@example.com")  # a plain patient - must not show up
    client.post(
        "/api/auth/register",
        json={"email": "pending2@example.com", "password": "strong-password", "full_name": "Dr. Two", "role": "dentist", "license_number": "LIC-2"},
    )
    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    response = client.get("/api/admin/dentist-requests", headers=headers)
    assert response.status_code == 200
    emails = [row["email"] for row in response.json()]
    assert "pending2@example.com" in emails
    assert "pending1@example.com" not in emails


def test_admin_can_approve_a_dentist_request(client):
    client.post(
        "/api/auth/register",
        json={"email": "approveme@example.com", "password": "strong-password", "full_name": "Dr. Approve", "role": "dentist", "license_number": "LIC-3"},
    )
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == "approveme@example.com").first().id

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    response = client.post(f"/api/admin/dentist-requests/{user_id}/approve", headers=headers, json={"notes": "Verified with PMDC registry"})
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.role.value == "dentist"
        assert user.dentist_verification_status == "approved"


def test_admin_can_reject_a_dentist_request_without_locking_out_the_account(client):
    client.post(
        "/api/auth/register",
        json={"email": "rejectme@example.com", "password": "strong-password", "full_name": "Dr. Reject", "role": "dentist", "license_number": "LIC-4"},
    )
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == "rejectme@example.com").first().id

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    response = client.post(f"/api/admin/dentist-requests/{user_id}/reject", headers=headers, json={"notes": "License number not found"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.role.value == "patient", "rejection must not lock the person out of the account they already have"
        assert user.dentist_verification_status == "rejected"


def test_approving_twice_is_rejected_with_a_clear_conflict(client):
    client.post(
        "/api/auth/register",
        json={"email": "twice@example.com", "password": "strong-password", "full_name": "Dr. Twice", "role": "dentist", "license_number": "LIC-5"},
    )
    with SessionLocal() as db:
        user_id = db.query(User).filter(User.email == "twice@example.com").first().id

    admin = create_admin_user()
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    first = client.post(f"/api/admin/dentist-requests/{user_id}/approve", headers=headers)
    assert first.status_code == 200
    second = client.post(f"/api/admin/dentist-requests/{user_id}/approve", headers=headers)
    assert second.status_code == 409


def test_dentist_requests_endpoint_requires_admin(client):
    patient = register_user(client, "not-an-admin@example.com")
    headers = {"Authorization": f"Bearer {patient['access_token']}"}

    response = client.get("/api/admin/dentist-requests", headers=headers)
    assert response.status_code == 403
