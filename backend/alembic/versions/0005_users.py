"""add users table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id',              sa.Integer(),     primary_key=True),
        sa.Column('username',        sa.String(64),    nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255),   nullable=False),
        sa.Column('role',            sa.String(16),    nullable=False, server_default='readonly'),
        sa.Column('enabled',         sa.Boolean(),     nullable=False, server_default='true'),
    )
    op.create_index('ix_users_username', 'users', ['username'])


def downgrade() -> None:
    op.drop_index('ix_users_username')
    op.drop_table('users')
