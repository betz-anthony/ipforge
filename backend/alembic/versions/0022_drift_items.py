"""generalize collisions into drift_items

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("collisions", "drift_items")
    op.alter_column("drift_items", "collision_type", new_column_name="category",
                    existing_type=sa.String(50), existing_nullable=False)
    op.add_column("drift_items", sa.Column("severity", sa.String(20), nullable=False, server_default="warning"))
    op.add_column("drift_items", sa.Column("subnet_id", sa.Integer,
                                           sa.ForeignKey("subnets.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_drift_items_subnet_id", "drift_items", ["subnet_id"])
    # rename the unique constraint where the backend supports it (PostgreSQL)
    try:
        op.execute("ALTER TABLE drift_items RENAME CONSTRAINT uq_collision_ip_type TO uq_drift_ip_category")
    except Exception:
        pass


def downgrade():
    try:
        op.execute("ALTER TABLE drift_items RENAME CONSTRAINT uq_drift_ip_category TO uq_collision_ip_type")
    except Exception:
        pass
    op.drop_index("ix_drift_items_subnet_id", table_name="drift_items")
    op.drop_column("drift_items", "subnet_id")
    op.drop_column("drift_items", "severity")
    op.alter_column("drift_items", "category", new_column_name="collision_type",
                    existing_type=sa.String(50), existing_nullable=False)
    op.rename_table("drift_items", "collisions")
