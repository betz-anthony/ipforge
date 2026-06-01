"""drift v2 — new categories + subnet-scoped policies

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    # Add subnet_id to drift_policies for per-subnet policy overrides.
    op.add_column("drift_policies",
                  sa.Column("subnet_id", sa.Integer,
                            sa.ForeignKey("subnets.id", ondelete="CASCADE"),
                            nullable=True))
    op.create_index("ix_drift_policies_subnet_id", "drift_policies", ["subnet_id"])

    # Replace per-category unique constraint with (category, subnet_id) pair.
    # Global policies (subnet_id IS NULL) uniqueness is enforced at app layer
    # since most SQL dialects treat NULL != NULL in UNIQUE constraints.
    op.drop_constraint("uq_drift_policies_category", "drift_policies", type_="unique")
    op.create_index("uq_drift_policies_category_subnet", "drift_policies",
                    ["category", "subnet_id"], unique=True)


def downgrade():
    op.drop_index("uq_drift_policies_category_subnet", table_name="drift_policies")
    op.drop_index("ix_drift_policies_subnet_id", table_name="drift_policies")
    op.drop_column("drift_policies", "subnet_id")
    op.create_unique_constraint("uq_drift_policies_category", "drift_policies", ["category"])
