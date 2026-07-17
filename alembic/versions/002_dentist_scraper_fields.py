"""Add dentist scraper fields for AKU data ingestion

Revision ID: 002_dentist_scraper
Revises: 001_initial
Create Date: 2025-01-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_dentist_scraper"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to dentists table
    dentist_columns = [
        ("slug", sa.String(300), {"nullable": True}),
        ("degrees", sa.String(500), {"nullable": True}),
        ("department", sa.String(255), {"nullable": True}),
        ("hospital", sa.String(255), {"nullable": True}),
        ("gender", sa.String(20), {"nullable": True}),
        ("consultation_timings", sa.Text(), {"nullable": True}),
        ("available_days", sa.String(255), {"nullable": True}),
        ("appointment_url", sa.String(1000), {"nullable": True}),
        ("areas_of_interest", sa.Text(), {"nullable": True}),
        ("clinical_interests", sa.Text(), {"nullable": True}),
        ("research_interests", sa.Text(), {"nullable": True}),
        ("education", sa.Text(), {"nullable": True}),
        ("certifications", sa.Text(), {"nullable": True}),
        ("awards", sa.Text(), {"nullable": True}),
        ("publications", sa.Text(), {"nullable": True}),
        ("memberships", sa.Text(), {"nullable": True}),
        ("image_url", sa.String(1000), {"nullable": True}),
        ("image_path", sa.String(1000), {"nullable": True}),
        ("profile_url", sa.String(1000), {"nullable": True}),
        ("phone", sa.String(50), {"nullable": True}),
        ("email", sa.String(255), {"nullable": True}),
        ("hospital_address", sa.Text(), {"nullable": True}),
        ("content_hash", sa.String(64), {"nullable": True}),
        ("data_version", sa.Integer(), {"nullable": False, "server_default": "1"}),
        ("last_scraped_at", sa.DateTime(timezone=True), {"nullable": True}),
    ]

    for col_name, col_type, kwargs in dentist_columns:
        try:
            op.add_column("dentists", sa.Column(col_name, col_type, **kwargs))
        except Exception:
            pass  # Column already exists

    # Create unique indexes
    try:
        op.create_index("ix_dentists_slug", "dentists", ["slug"], unique=True)
    except Exception:
        pass

    try:
        op.create_index("ix_dentists_profile_url", "dentists", ["profile_url"], unique=True)
    except Exception:
        pass

    try:
        op.create_index("ix_dentists_content_hash", "dentists", ["content_hash"], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    columns_to_drop = [
        "slug", "degrees", "department", "hospital", "gender",
        "consultation_timings", "available_days", "appointment_url",
        "areas_of_interest", "clinical_interests", "research_interests",
        "education", "certifications", "awards", "publications", "memberships",
        "image_url", "image_path", "profile_url", "phone", "email",
        "hospital_address", "content_hash", "data_version", "last_scraped_at",
    ]

    indexes_to_drop = [
        "ix_dentists_slug",
        "ix_dentists_profile_url",
        "ix_dentists_content_hash",
    ]

    for idx_name in indexes_to_drop:
        try:
            op.drop_index(idx_name, table_name="dentists")
        except Exception:
            pass

    for col_name in columns_to_drop:
        try:
            op.drop_column("dentists", col_name)
        except Exception:
            pass
