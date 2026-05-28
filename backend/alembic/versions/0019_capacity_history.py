"""subnet utilization history for capacity forecasting

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "subnet_utilization_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subnet_id", sa.Integer, sa.ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("used_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("subnet_id", "date", name="uq_subnet_util_date"),
    )
    op.create_index("ix_subnet_utilization_history_subnet_id", "subnet_utilization_history", ["subnet_id"])


def downgrade():
    op.drop_index("ix_subnet_utilization_history_subnet_id", table_name="subnet_utilization_history")
    op.drop_table("subnet_utilization_history")
