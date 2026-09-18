"""subnet_ranges.source + cache_dhcp_scope_pools

DHCP-RESERVED-RANGE-SYNC-001. source distinguishes a provider-synced
Reserved Range (non-null: the provider that wrote it) from a manual one
(null — 100% of existing rows, unchanged). cache_dhcp_scope_pools holds
every pool range per DHCP scope (a Kea subnet can have more than one;
msdhcp/pihole get exactly one row each) — the input for deriving
exclusion ranges.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subnet_ranges") as batch:
        batch.add_column(sa.Column("source", sa.String(100), nullable=True))
        batch.create_index("ix_subnet_ranges_source", ["source"])

    op.create_table(
        "cache_dhcp_scope_pools",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scope_id", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("start_ip", sa.String, nullable=False),
        sa.Column("end_ip", sa.String, nullable=False),
    )
    op.create_index("ix_cache_dhcp_scope_pools_scope_id", "cache_dhcp_scope_pools", ["scope_id"])
    op.create_index("ix_cache_dhcp_scope_pools_source", "cache_dhcp_scope_pools", ["source"])


def downgrade():
    op.drop_index("ix_cache_dhcp_scope_pools_source", table_name="cache_dhcp_scope_pools")
    op.drop_index("ix_cache_dhcp_scope_pools_scope_id", table_name="cache_dhcp_scope_pools")
    op.drop_table("cache_dhcp_scope_pools")

    with op.batch_alter_table("subnet_ranges") as batch:
        batch.drop_index("ix_subnet_ranges_source")
        batch.drop_column("source")
