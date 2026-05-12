"""add provider_configs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'provider_configs',
        sa.Column('id',            sa.Integer(),     primary_key=True),
        sa.Column('category',      sa.String(16),    nullable=False),
        sa.Column('provider_type', sa.String(32),    nullable=False),
        sa.Column('name',          sa.String(64),    nullable=False, unique=True),
        sa.Column('config',        sa.Text(),        nullable=False, server_default='{}'),
        sa.Column('enabled',       sa.Boolean(),     nullable=False, server_default='true'),
        sa.Column('sort_order',    sa.Integer(),     nullable=False, server_default='0'),
    )
    op.create_index('ix_provider_configs_category', 'provider_configs', ['category', 'enabled'])


def downgrade() -> None:
    op.drop_index('ix_provider_configs_category')
    op.drop_table('provider_configs')
