"""drift auto-remediation: policies + needs_review

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("drift_items", sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table(
        "drift_policies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category", name="uq_drift_policies_category"),
    )


def downgrade():
    op.drop_table("drift_policies")
    op.drop_column("drift_items", "needs_review")
