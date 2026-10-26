"""Owned investigation graph, evidence, tool trace and evaluation records."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("runner_id", sa.String(36), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(20), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        *[
            sa.Column(k, sa.JSON(), nullable=False)
            for k in ("request", "context", "provider", "usage", "verification")
        ],
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("cancel_requested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
    )
    op.create_index("ix_agent_investigations_owner", "agent_investigations", ["owner"])
    for table in ("agent_steps", "agent_tool_calls", "agent_evidence"):
        columns = [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "investigation_id",
                sa.String(36),
                sa.ForeignKey("agent_investigations.id"),
                nullable=False,
            ),
        ]
        if table == "agent_steps":
            columns.append(sa.Column("sequence", sa.Integer(), nullable=False))
        columns.append(sa.Column("payload", sa.JSON(), nullable=False))
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_investigation_id", table, ["investigation_id"])
    op.create_table(
        "agent_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_evaluations_owner", "agent_evaluations", ["owner"])


def downgrade():
    for table in (
        "agent_evaluations",
        "agent_evidence",
        "agent_tool_calls",
        "agent_steps",
        "agent_investigations",
    ):
        op.drop_table(table)
