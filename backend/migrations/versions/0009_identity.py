"""Add durable accounts/sessions and preserve legacy owner keys as unclaimed workspaces."""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

OWNER_TABLES = (
    "datasets",
    "risk_runs",
    "portfolio_snapshots",
    "risk_input_artifacts",
    "research_experiments",
    "forecast_models",
    "model_governance_events",
    "agent_investigations",
    "agent_evaluations",
    "research_documents",
    "research_document_chunks",
    "optimization_runs",
    "optimization_counterfactuals",
    "governance_models",
    "governance_review_events",
)


def upgrade():
    # Additive identity tables; no financial payload, source ID or result hash is rewritten.
    # Definitions are frozen here instead of invoking mutable application create_all.
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preferred_scope", sa.String(64)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "ownership_scopes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ownership_scopes_user_id", "ownership_scopes", ["user_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope_id", sa.String(64), sa.ForeignKey("ownership_scopes.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.Integer(), nullable=False),
        sa.Column("oauth_state_hash", sa.String(64)),
        sa.Column("oauth_state_expires", sa.Integer()),
        sa.Column("revoked", sa.Integer(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires", "auth_sessions", ["expires"])
    op.create_table("roles", sa.Column("name", sa.String(32), primary_key=True))
    op.bulk_insert(
        sa.table("roles", sa.column("name", sa.String(32))),
        [{"name": n} for n in ("USER", "RESEARCH_REVIEWER", "RESEARCH_ADMIN", "PLATFORM_ADMIN")],
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(32), sa.ForeignKey("roles.name"), primary_key=True),
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for key in ("actor_id", "action"):
        op.create_index(f"ix_security_events_{key}", "security_events", [key])
    op.create_table(
        "auth_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("bucket", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "recovery_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
    )
    op.create_index("ix_recovery_tokens_user_id", "recovery_tokens", ["user_id"])
    op.create_table(
        "review_assignments",
        sa.Column(
            "model_id", sa.String(36), sa.ForeignKey("governance_models.id"), primary_key=True
        ),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
    )
    connection = op.get_bind()
    scopes = sa.table(
        "ownership_scopes",
        sa.column("id", sa.String(64)),
        sa.column("user_id", sa.String(36)),
        sa.column("name", sa.String(100)),
        sa.column("kind", sa.String(20)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    seen = set()
    for table in OWNER_TABLES:
        for ident in connection.execute(sa.text(f'SELECT DISTINCT owner FROM "{table}"')).scalars():
            if ident not in seen:
                connection.execute(
                    scopes.insert().values(
                        id=ident,
                        user_id=None,
                        name="Unclaimed legacy research",
                        kind="legacy",
                        created_at=datetime.now(UTC),
                    )
                )
                seen.add(ident)
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                f"fk_{table}_ownership_scope", "ownership_scopes", ["owner"], ["id"]
            )


def downgrade():
    connection = op.get_bind()
    if (
        connection.execute(sa.text("SELECT count(*) FROM users")).scalar_one()
        or connection.execute(sa.text("SELECT count(*) FROM security_events")).scalar_one()
    ):
        raise RuntimeError(
            "Populated identity migration is forward-only. Restore a coordinated pre-upgrade backup to revert."
        )
    for table in reversed(OWNER_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_ownership_scope", type_="foreignkey")
    for table in (
        "review_assignments",
        "recovery_tokens",
        "auth_throttles",
        "security_events",
        "user_role_assignments",
        "roles",
        "auth_sessions",
        "ownership_scopes",
        "users",
    ):
        op.drop_table(table)
