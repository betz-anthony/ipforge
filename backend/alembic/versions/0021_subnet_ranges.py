"""subnet reserved/excluded ranges

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subnet_ranges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subnet_id", sa.Integer, sa.ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_ip", sa.String(50), nullable=False),
        sa.Column("end_ip", sa.String(50), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subnet_ranges_subnet_id", "subnet_ranges", ["subnet_id"])


def downgrade():
    op.drop_index("ix_subnet_ranges_subnet_id", table_name="subnet_ranges")
    op.drop_table("subnet_ranges")
