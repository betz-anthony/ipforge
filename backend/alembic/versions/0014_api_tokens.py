"""add api_tokens table

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'api_tokens',
        sa.Column('id',           sa.Integer(), primary_key=True),
        sa.Column('user_id',      sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name',         sa.String(64), nullable=False),
        sa.Column('token_hash',   sa.String(64), nullable=False),
        sa.Column('token_prefix', sa.String(16), nullable=False),
        sa.Column('read_only',    sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('expires_at',   sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at',   sa.DateTime(), nullable=True),
    )
    op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'])
    op.create_index('ix_api_tokens_token_hash', 'api_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_api_tokens_token_hash', table_name='api_tokens')
    op.drop_index('ix_api_tokens_user_id', table_name='api_tokens')
    op.drop_table('api_tokens')
