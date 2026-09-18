"""ip_sort_key on ip_addresses + cache_dhcp_leases

Numeric (not lexicographic) IP sort. Adds a 16-byte packed sort key —
IPv4-mapped into the same 16-byte space IPv6 occupies — kept in sync by an
ORM event listener (app/core/ip_sort_events.py) on every future write; this
migration backfills existing rows once.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-19
"""
import ipaddress

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def _ip_sort_key(ip: str) -> bytes | None:
    try:
        return ipaddress.ip_address(ip).packed.rjust(16, b"\x00")
    except ValueError:
        return None


def _backfill(table: str, id_col: str, ip_col: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT {id_col}, {ip_col} FROM {table}")).fetchall()
    for row_id, ip in rows:
        key = _ip_sort_key(ip)
        if key is not None:
            bind.execute(
                sa.text(f"UPDATE {table} SET ip_sort_key = :key WHERE {id_col} = :id"),
                {"key": key, "id": row_id},
            )


def upgrade():
    op.add_column("ip_addresses", sa.Column("ip_sort_key", sa.LargeBinary(16), nullable=True))
    op.create_index("ix_ip_addresses_ip_sort_key", "ip_addresses", ["ip_sort_key"])
    op.add_column("cache_dhcp_leases", sa.Column("ip_sort_key", sa.LargeBinary(16), nullable=True))
    op.create_index("ix_cache_dhcp_leases_ip_sort_key", "cache_dhcp_leases", ["ip_sort_key"])

    _backfill("ip_addresses", "id", "address")
    _backfill("cache_dhcp_leases", "id", "ip_address")


def downgrade():
    op.drop_index("ix_cache_dhcp_leases_ip_sort_key", table_name="cache_dhcp_leases")
    op.drop_column("cache_dhcp_leases", "ip_sort_key")
    op.drop_index("ix_ip_addresses_ip_sort_key", table_name="ip_addresses")
    op.drop_column("ip_addresses", "ip_sort_key")
