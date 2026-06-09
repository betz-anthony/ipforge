"""pagination indexes for efficient ordered queries

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-09
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    # Hostname index supports ORDER BY hostname; ILIKE '%..%' is seq-scan regardless
    op.create_index("ix_ip_addresses_hostname", "ip_addresses", ["hostname"])

    # Cache DNS records by zone + name (for sorted iteration)
    op.create_index(
        "ix_cache_dns_records_zone_name", "cache_dns_records",
        ["zone", "name"]
    )

    # Cache DHCP leases by scope + IP (for sorted iteration)
    op.create_index(
        "ix_cache_dhcp_leases_scope_ip", "cache_dhcp_leases",
        ["scope_id", "ip_address"]
    )

    # Audit log by timestamp + id (for keyset pagination)
    op.create_index(
        "ix_audit_log_timestamp_id", "audit_log",
        ["timestamp", "id"]
    )


def downgrade():
    op.drop_index("ix_audit_log_timestamp_id", table_name="audit_log")
    op.drop_index("ix_cache_dhcp_leases_scope_ip", table_name="cache_dhcp_leases")
    op.drop_index("ix_cache_dns_records_zone_name", table_name="cache_dns_records")
    op.drop_index("ix_ip_addresses_hostname", table_name="ip_addresses")
