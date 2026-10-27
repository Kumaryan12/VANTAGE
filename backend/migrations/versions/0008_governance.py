"""Explicit local research review states and authorized human audit events."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "governance_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("model_type", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("intended_use", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner", "source_type", "source_id"),
    )
    op.create_index("ix_governance_models_owner", "governance_models", ["owner"])
    op.create_table(
        "governance_review_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("governance_models.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_governance_review_events_owner", "governance_review_events", ["owner"])
    op.create_index(
        "ix_governance_review_events_model_id", "governance_review_events", ["model_id"]
    )


def downgrade():
    op.drop_table("governance_review_events")
    op.drop_table("governance_models")
