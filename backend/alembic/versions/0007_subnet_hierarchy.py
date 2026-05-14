"""add parent_id to subnets

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subnets', sa.Column('parent_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_subnets_parent_id', 'subnets', 'subnets', ['parent_id'], ['id']
    )
    op.create_index('ix_subnets_parent_id', 'subnets', ['parent_id'])


def downgrade() -> None:
    op.drop_index('ix_subnets_parent_id', table_name='subnets')
    op.drop_constraint('fk_subnets_parent_id', 'subnets', type_='foreignkey')
    op.drop_column('subnets', 'parent_id')
