"""automation rules engine

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("condition", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("action", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_automation_rules_name"),
    )


def downgrade():
    op.drop_table("automation_rules")
