"""Immutable snapshots/estimation inputs and typed Phase 2 run records."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("portfolio_snapshots", "risk_input_artifacts"):
        op.create_table(
            name,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("owner", "content_hash"),
        )
        op.create_index(f"ix_{name}_owner", name, ["owner"])
    with op.batch_alter_table("risk_runs") as batch:
        batch.add_column(
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="legacy"))
        batch.add_column(sa.Column("snapshot_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("input_artifact_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("parameters", sa.JSON(), nullable=True))
        batch.create_foreign_key("fk_run_snapshot", "portfolio_snapshots", ["snapshot_id"], ["id"])
        batch.create_foreign_key(
            "fk_run_artifact", "risk_input_artifacts", ["input_artifact_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("risk_runs") as batch:
        batch.drop_constraint("fk_run_snapshot", type_="foreignkey")
        batch.drop_constraint("fk_run_artifact", type_="foreignkey")
        for name in ("parameters", "input_artifact_id", "snapshot_id", "kind", "schema_version"):
            batch.drop_column(name)
    op.drop_table("risk_input_artifacts")
    op.drop_table("portfolio_snapshots")
