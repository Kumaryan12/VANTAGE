"""Private page-aware document library and bounded keyword/vector index."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("company", sa.String(80), nullable=True),
        sa.Column("reporting_period", sa.String(50), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("processing", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
    )
    op.create_index("ix_research_documents_owner", "research_documents", ["owner"])
    op.create_table(
        "research_document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column(
            "document_id", sa.String(36), sa.ForeignKey("research_documents.id"), nullable=False
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(150), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_counts", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.create_index("ix_research_document_chunks_owner", "research_document_chunks", ["owner"])
    op.create_index(
        "ix_research_document_chunks_document_id", "research_document_chunks", ["document_id"]
    )


def downgrade():
    op.drop_table("research_document_chunks")
    op.drop_table("research_documents")
