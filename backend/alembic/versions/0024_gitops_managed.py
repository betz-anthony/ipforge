"""gitops managed-resource markers

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gitops_managed",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_gitops_managed_resource"),
    )
    op.create_index("ix_gitops_managed_source", "gitops_managed", ["source"])


def downgrade():
    op.drop_index("ix_gitops_managed_source", table_name="gitops_managed")
    op.drop_table("gitops_managed")
