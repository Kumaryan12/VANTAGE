"""Immutable optimization experiments, bounded studies and counterfactual comparisons."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(150), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("runner_id", sa.String(36), nullable=False),
        sa.Column(
            "snapshot_id", sa.String(36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False
        ),
        sa.Column(
            "artifact_id", sa.String(36), sa.ForeignKey("risk_input_artifacts.id"), nullable=False
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        *[sa.Column(k, sa.JSON(), nullable=False) for k in ("parameters", "dataset", "runtime")],
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("reproduction_of", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_optimization_runs_owner", "optimization_runs", ["owner"])
    op.create_table(
        "optimization_counterfactuals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("optimization_runs.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_optimization_counterfactuals_owner", "optimization_counterfactuals", ["owner"]
    )
    op.create_index(
        "ix_optimization_counterfactuals_run_id", "optimization_counterfactuals", ["run_id"]
    )


def downgrade():
    op.drop_table("optimization_counterfactuals")
    op.drop_table("optimization_runs")
