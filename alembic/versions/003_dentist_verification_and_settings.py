"""Add dentist verification request fields and previously-unpersisted settings fields

Phase 8: closes two gaps documented in docs/PRODUCT_BENCHMARK.md - finding #1 (dentist
registration was rejected outright with no admin-side way to ever grant one) and finding
#4 (the Settings page's Chat History Retention control, plus several other toggles,
were sent by the frontend but had no matching backend column at all, so they were
silently dropped on every save).

Revision ID: 003_dentist_verification
Revises: 002_dentist_scraper
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_dentist_verification"
down_revision: Union[str, None] = "002_dentist_scraper"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_columns = [
        ("dentist_verification_status", sa.String(20), {"nullable": False, "server_default": "none"}),
        ("dentist_license_number", sa.String(100), {"nullable": True}),
        ("dentist_clinic_name", sa.String(255), {"nullable": True}),
        ("dentist_verification_requested_at", sa.DateTime(timezone=True), {"nullable": True}),
        ("dentist_verification_notes", sa.Text(), {"nullable": True}),
    ]
    for col_name, col_type, kwargs in user_columns:
        try:
            op.add_column("users", sa.Column(col_name, col_type, **kwargs))
        except Exception:
            pass  # Column already exists (e.g. re-run, or created fresh via create_all)

    settings_columns = [
        ("push_notifications", sa.Boolean(), {"nullable": False, "server_default": sa.true()}),
        ("data_sharing_consent", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
        ("hipaa_consent", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
        ("ai_disclaimer_acknowledged", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
        ("chat_history_retention_days", sa.Integer(), {"nullable": False, "server_default": "90"}),
    ]
    for col_name, col_type, kwargs in settings_columns:
        try:
            op.add_column("user_settings", sa.Column(col_name, col_type, **kwargs))
        except Exception:
            pass


def downgrade() -> None:
    for col_name in ["push_notifications", "data_sharing_consent", "hipaa_consent", "ai_disclaimer_acknowledged", "chat_history_retention_days"]:
        try:
            op.drop_column("user_settings", col_name)
        except Exception:
            pass

    for col_name in [
        "dentist_verification_status", "dentist_license_number", "dentist_clinic_name",
        "dentist_verification_requested_at", "dentist_verification_notes",
    ]:
        try:
            op.drop_column("users", col_name)
        except Exception:
            pass
