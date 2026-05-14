"""add audit_log table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id',            sa.Integer(),    primary_key=True),
        sa.Column('timestamp',     sa.DateTime(),   nullable=False),
        sa.Column('username',      sa.String(64),   nullable=False),
        sa.Column('action',        sa.String(16),   nullable=False),
        sa.Column('resource_type', sa.String(32),   nullable=False),
        sa.Column('resource_id',   sa.String(128),  nullable=False),
        sa.Column('summary',       sa.Text(),       nullable=True),
        sa.Column('before_state',  sa.Text(),       nullable=True),
        sa.Column('after_state',   sa.Text(),       nullable=True),
    )
    op.create_index('ix_audit_log_timestamp',     'audit_log', ['timestamp'])
    op.create_index('ix_audit_log_resource_type', 'audit_log', ['resource_type'])
    op.create_index('ix_audit_log_username',      'audit_log', ['username'])


def downgrade() -> None:
    op.drop_index('ix_audit_log_username')
    op.drop_index('ix_audit_log_resource_type')
    op.drop_index('ix_audit_log_timestamp')
    op.drop_table('audit_log')
