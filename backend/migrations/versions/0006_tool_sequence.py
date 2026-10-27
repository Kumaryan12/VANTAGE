"""Persist actual agent call order; legacy ordering remains unknown."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_tool_calls", sa.Column("sequence", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("agent_tool_calls", "sequence")
