"""webhook endpoints + deliveries (WEBHOOK-OUT-001)

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("secret_enc", sa.Text, nullable=True),
        sa.Column("custom_headers", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("resource_types", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("actions", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("endpoint_id", sa.Integer,
                  sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime, nullable=False),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_webhook_deliveries_due", "webhook_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_webhook_deliveries_endpoint", "webhook_deliveries", ["endpoint_id"])


def downgrade():
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
