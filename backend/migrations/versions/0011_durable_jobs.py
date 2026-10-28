"""SQL job outbox, fenced leases and distributed admission gates."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operation_gates",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("paused", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), sa.ForeignKey("ownership_scopes.id"), nullable=False),
        sa.Column("principal", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("input_reference", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("worker_id", sa.String(100)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("failure", sa.JSON()),
        sa.Column("result_reference", sa.JSON()),
        sa.Column("attempt_history", sa.JSON(), nullable=False),
        sa.UniqueConstraint("owner", "kind", "idempotency_key"),
    )
    for name in (
        "owner",
        "principal",
        "kind",
        "target_id",
        "status",
        "available_at",
        "lease_expires",
    ):
        op.create_index(f"ix_background_jobs_{name}", "background_jobs", [name])
    op.bulk_insert(
        sa.table("operation_gates", sa.column("id", sa.String), sa.column("paused", sa.Integer)),
        [{"id": "jobs", "paused": 0}],
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM background_jobs")).scalar_one():
        raise RuntimeError(
            "Populated job evidence requires forward recovery or coordinated restore."
        )
    op.drop_table("background_jobs")
    op.drop_table("operation_gates")
