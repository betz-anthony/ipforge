"""ip request workflow

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "subnets",
        sa.Column("request_eligible", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "ip_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("requester_username", sa.String(64), nullable=False),
        sa.Column("subnet_id", sa.Integer, sa.ForeignKey("subnets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hostname", sa.String(63), nullable=False),
        sa.Column("mac_address", sa.String(17), nullable=True),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewer_username", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("allocated_ip", sa.String(45), nullable=True),
        sa.Column("allocated_id", sa.Integer, sa.ForeignKey("ip_addresses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ip_requests_status_created", "ip_requests", ["status", "created_at"])
    op.create_index("ix_ip_requests_requester_status", "ip_requests", ["requester_username", "status"])


def downgrade():
    op.drop_index("ix_ip_requests_requester_status", table_name="ip_requests")
    op.drop_index("ix_ip_requests_status_created", table_name="ip_requests")
    op.drop_table("ip_requests")
    op.drop_column("subnets", "request_eligible")
