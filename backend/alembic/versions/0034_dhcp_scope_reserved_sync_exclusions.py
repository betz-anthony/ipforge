"""dhcp_scope_reserved_sync_exclusions

Admin-set opt-out per (source, scope_id): a scope listed here keeps syncing
leases/pools normally, but its gateway/exclusions are withheld from the
Reserved Ranges auto-sync — for scopes kept in DHCP for testing/monitoring
rather than real distribution.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dhcp_scope_reserved_sync_exclusions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("source", "scope_id", name="uq_dhcp_scope_reserved_sync_exclusions"),
    )
    op.create_index(
        "ix_dhcp_scope_reserved_sync_exclusions_source",
        "dhcp_scope_reserved_sync_exclusions", ["source"],
    )


def downgrade():
    op.drop_index("ix_dhcp_scope_reserved_sync_exclusions_source", table_name="dhcp_scope_reserved_sync_exclusions")
    op.drop_table("dhcp_scope_reserved_sync_exclusions")
