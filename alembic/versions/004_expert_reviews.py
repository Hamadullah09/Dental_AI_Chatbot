"""Add expert_reviews table for the human expert review workflow

Phase 8: a domain expert deliberately sampling real conversations against a fixed
faithfulness/safety/citation-accuracy rubric, distinct from the user-submitted Feedback
table - see docs/adr/0016-human-review-workflow-for-unreviewed-conversations.md.

Revision ID: 004_expert_reviews
Revises: 003_dentist_verification
Create Date: 2026-07-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_expert_reviews"
down_revision: Union[str, None] = "003_dentist_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expert_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("faithfulness", sa.String(20), nullable=False),
        sa.Column("safety", sa.String(20), nullable=False),
        sa.Column("citation_accuracy", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_expert_reviews_message_id", "expert_reviews", ["message_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_expert_reviews_message_id", table_name="expert_reviews")
    op.drop_table("expert_reviews")
