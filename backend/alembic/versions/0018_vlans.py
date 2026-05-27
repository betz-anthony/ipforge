"""vlan catalog

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vlans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("vlan_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("vlan_id", name="uq_vlans_vlan_id"),
    )
    op.create_index("ix_vlans_vlan_id", "vlans", ["vlan_id"])


def downgrade():
    op.drop_index("ix_vlans_vlan_id", table_name="vlans")
    op.drop_table("vlans")
