"""snmp discovery: network_devices + discovered_endpoints

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "network_devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("snmp_version", sa.String(4), nullable=False, server_default="2c"),
        sa.Column("community", sa.String(512), nullable=True),
        sa.Column("v3_user", sa.String(255), nullable=True),
        sa.Column("auth_protocol", sa.String(16), nullable=True),
        sa.Column("auth_key", sa.String(512), nullable=True),
        sa.Column("priv_protocol", sa.String(16), nullable=True),
        sa.Column("priv_key", sa.String(512), nullable=True),
        sa.Column("security_level", sa.String(20), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "discovered_endpoints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip", sa.String(50), nullable=True),
        sa.Column("mac", sa.String(50), nullable=False),
        sa.Column("ifindex", sa.Integer, nullable=True),
        sa.Column("port_name", sa.String(128), nullable=True),
        sa.Column("vlan", sa.Integer, nullable=True),
        sa.Column("last_seen", sa.DateTime, nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
    )
    op.create_index("ix_discovered_endpoints_device_id", "discovered_endpoints", ["device_id"])
    op.create_index("ix_discovered_endpoints_ip", "discovered_endpoints", ["ip"])
    op.create_index("ix_discovered_endpoints_mac", "discovered_endpoints", ["mac"])


def downgrade():
    op.drop_index("ix_discovered_endpoints_mac", table_name="discovered_endpoints")
    op.drop_index("ix_discovered_endpoints_ip", table_name="discovered_endpoints")
    op.drop_index("ix_discovered_endpoints_device_id", table_name="discovered_endpoints")
    op.drop_table("discovered_endpoints")
    op.drop_table("network_devices")
