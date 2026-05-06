"""add notes to subnets and ip_addresses

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subnets', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('ip_addresses', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('ip_addresses', 'notes')
    op.drop_column('subnets', 'notes')
