"""dhcp_scope_subnet_autocreate_exclusions

Per-scope opt-out for creating IPAM subnets from DHCP scopes.

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dhcp_scope_subnet_autocreate_exclusions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("source", "scope_id", name="uq_dhcp_scope_subnet_autocreate_exclusions"),
    )
    op.create_index(
        "ix_dhcp_scope_subnet_autocreate_exclusions_source",
        "dhcp_scope_subnet_autocreate_exclusions", ["source"],
    )


def downgrade():
    op.drop_index("ix_dhcp_scope_subnet_autocreate_exclusions_source",
                  table_name="dhcp_scope_subnet_autocreate_exclusions")
    op.drop_table("dhcp_scope_subnet_autocreate_exclusions")
