"""widen cache_dhcp_leases.iaid to BIGINT

DHCPv6 IAID is an unsigned 32-bit value (RFC 8415 §4.2); values above
2147483647 overflow a Postgres INTEGER column and abort the DHCP sync flush.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cache_dhcp_leases") as batch:
        batch.alter_column(
            "iaid",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
            existing_server_default="0",
        )


def downgrade():
    with op.batch_alter_table("cache_dhcp_leases") as batch:
        batch.alter_column(
            "iaid",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
            existing_server_default="0",
        )
