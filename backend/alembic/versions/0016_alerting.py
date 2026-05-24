"""alerting tables

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-24

Note: The pre-existing 'alert_events' table (owned by the scan module) is left
untouched. The alerting system uses 'alerting_events', 'alert_channels', and
'alert_rules' to avoid naming conflicts.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("config", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("secret_enc", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("condition", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("channel_ids", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recipients", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("renotify_minutes", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "alerting_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule_id", sa.Integer, sa.ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resource_key", sa.String(128), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("first_fired_at", sa.DateTime, nullable=False),
        sa.Column("last_fired_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("deliveries", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_index("ix_alerting_events_dedupe", "alerting_events", ["rule_id", "resource_key", "state"])
    op.create_index("ix_alerting_events_state_fired", "alerting_events", ["state", "first_fired_at"])


def downgrade():
    op.drop_index("ix_alerting_events_state_fired", table_name="alerting_events")
    op.drop_index("ix_alerting_events_dedupe", table_name="alerting_events")
    op.drop_table("alerting_events")
    op.drop_table("alert_rules")
    op.drop_table("alert_channels")
