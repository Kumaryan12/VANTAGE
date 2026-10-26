"""Research jobs, portable model registry, dated forecasts and governance."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(150), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("runner_id", sa.String(36), nullable=False),
        sa.Column(
            "snapshot_id", sa.String(36), sa.ForeignKey("portfolio_snapshots.id"), nullable=False
        ),
        sa.Column(
            "input_artifact_id",
            sa.String(36),
            sa.ForeignKey("risk_input_artifacts.id"),
            nullable=False,
        ),
        sa.Column("dataset_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        *[
            sa.Column(k, sa.JSON(), nullable=False)
            for k in ("parameters", "data_info", "protocol", "runtime")
        ],
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("reproduction_of", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_research_experiments_owner", "research_experiments", ["owner"])
    op.create_table(
        "forecast_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column(
            "experiment_id", sa.String(36), sa.ForeignKey("research_experiments.id"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_forecast_models_owner", "forecast_models", ["owner"])
    op.create_index("ix_forecast_models_experiment_id", "forecast_models", ["experiment_id"])
    op.create_table(
        "research_forecasts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("forecast_models.id"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("model_id", "target_date"),
    )
    op.create_index("ix_research_forecasts_model_id", "research_forecasts", ["model_id"])
    op.create_table(
        "model_governance_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("forecast_models.id"), nullable=False),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_governance_events_model_id", "model_governance_events", ["model_id"])


def downgrade():
    for table in (
        "model_governance_events",
        "research_forecasts",
        "forecast_models",
        "research_experiments",
    ):
        op.drop_table(table)
