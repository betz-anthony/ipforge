"""stale ip reclamation dismissed_until column

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ip_addresses',
        sa.Column('reclaim_dismissed_until', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('ip_addresses', 'reclaim_dismissed_until')
