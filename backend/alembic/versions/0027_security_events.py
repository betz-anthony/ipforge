"""security events + mac_last_seen

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("mac", sa.String(50), nullable=True),
        sa.Column("ip", sa.String(50), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("detected_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_at", sa.DateTime, nullable=True),
        sa.Column("quarantined", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_mac", "security_events", ["mac"])
    op.create_index("ix_security_events_ip", "security_events", ["ip"])
    op.create_table(
        "mac_last_seen",
        sa.Column("mac", sa.String(50), primary_key=True),
        sa.Column("device_id", sa.Integer, nullable=True),
        sa.Column("port_name", sa.String(128), nullable=True),
        sa.Column("ip", sa.String(50), nullable=True),
        sa.Column("last_seen", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("mac_last_seen")
    op.drop_index("ix_security_events_ip", table_name="security_events")
    op.drop_index("ix_security_events_mac", table_name="security_events")
    op.drop_index("ix_security_events_event_type", table_name="security_events")
    op.drop_table("security_events")
