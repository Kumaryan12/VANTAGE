"""Encrypted provider credentials, private object manifests and deletion requests."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ownership_scopes",
        sa.Column("lifecycle", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), sa.ForeignKey("ownership_scopes.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner", "provider"),
    )
    op.create_index("ix_provider_credentials_owner", "provider_credentials", ["owner"])
    op.create_table(
        "private_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), sa.ForeignKey("ownership_scopes.id"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("backend", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.String(150), nullable=False, unique=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("parent_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    for name in ("owner", "status", "parent_id"):
        op.create_index(f"ix_private_artifacts_{name}", "private_artifacts", [name])
    op.create_table(
        "deletion_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), sa.ForeignKey("ownership_scopes.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.JSON(), nullable=False),
    )
    op.create_index("ix_deletion_requests_owner", "deletion_requests", ["owner"])


def downgrade():
    if any(
        op.get_bind().execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar_one()
        for t in ("provider_credentials", "private_artifacts", "deletion_requests")
    ):
        raise RuntimeError(
            "Populated credential/storage migrations require coordinated restore or forward recovery."
        )
    for table in ("deletion_requests", "private_artifacts", "provider_credentials"):
        op.drop_table(table)
    with op.batch_alter_table("ownership_scopes") as batch:
        batch.drop_column("lifecycle")
