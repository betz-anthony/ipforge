"""custom fields and tags

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "custom_field_defs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("options", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("entity_type", "name", name="uq_custom_field_entity_name"),
    )
    op.create_table(
        "custom_field_values",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("field_id", sa.Integer, sa.ForeignKey("custom_field_defs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.UniqueConstraint("field_id", "entity_id", name="uq_custom_field_value"),
    )
    op.create_index("ix_custom_field_values_field_id", "custom_field_values", ["field_id"])
    op.create_index("ix_custom_field_values_entity_id", "custom_field_values", ["entity_id"])
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.UniqueConstraint("name", name="uq_tags_name"),
    )
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_table(
        "tag_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("tag_id", "entity_type", "entity_id", name="uq_tag_assignment"),
    )
    op.create_index("ix_tag_assignments_tag_id", "tag_assignments", ["tag_id"])
    op.create_index("ix_tag_assignments_entity_id", "tag_assignments", ["entity_id"])


def downgrade():
    op.drop_table("tag_assignments")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_custom_field_values_entity_id", table_name="custom_field_values")
    op.drop_index("ix_custom_field_values_field_id", table_name="custom_field_values")
    op.drop_table("custom_field_values")
    op.drop_table("custom_field_defs")
