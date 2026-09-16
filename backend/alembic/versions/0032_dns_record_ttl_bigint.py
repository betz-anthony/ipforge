"""widen cache_dns_records.ttl to BIGINT

DNS TTL is nominally a 32-bit value, but msdns's get_records() cast
TimeToLive.TotalSeconds through PowerShell [int] (System.Int32, signed,
max 2147483647) — a record with a TTL above that (legal on the wire,
just unusual) threw a PowerShell conversion error and aborted the whole
zone's sync. Fixing the cast to [int64] still needs a wide-enough column
to store the result — same shape as 0031's DHCP IAID fix.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cache_dns_records") as batch:
        batch.alter_column(
            "ttl",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
            existing_server_default="3600",
        )


def downgrade():
    with op.batch_alter_table("cache_dns_records") as batch:
        batch.alter_column(
            "ttl",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
            existing_server_default="3600",
        )
