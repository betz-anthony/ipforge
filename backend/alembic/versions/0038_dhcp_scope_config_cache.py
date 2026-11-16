"""dhcp_scope_config_cache

Scope-defined DHCP options and lease duration, cached by sync.

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cache_dhcp_scope_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("lease_seconds", sa.Integer(), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source", "scope_id", name="uq_cache_dhcp_scope_config"),
    )
    op.create_index("ix_cache_dhcp_scope_config_source", "cache_dhcp_scope_config", ["source"])


def downgrade():
    op.drop_index("ix_cache_dhcp_scope_config_source", table_name="cache_dhcp_scope_config")
    op.drop_table("cache_dhcp_scope_config")
