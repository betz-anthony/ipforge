"""subnet_pools

Named allocation windows inside a subnet; the allocate API can target one.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subnet_pools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subnet_id", sa.Integer(), sa.ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("start_ip", sa.String(50), nullable=False),
        sa.Column("end_ip", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("subnet_id", "name", name="uq_subnet_pools_subnet_name"),
    )
    op.create_index("ix_subnet_pools_subnet_id", "subnet_pools", ["subnet_id"])


def downgrade():
    op.drop_index("ix_subnet_pools_subnet_id", table_name="subnet_pools")
    op.drop_table("subnet_pools")
