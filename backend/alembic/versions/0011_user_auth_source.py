"""add auth_source to users

Revision ID: 0011
Revises: 0009
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('auth_source', sa.String(length=16),
                                     server_default='local', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'auth_source')
