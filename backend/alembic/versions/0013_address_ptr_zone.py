"""add ptr_zone to ip_addresses

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ip_addresses', sa.Column('ptr_zone', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('ip_addresses', 'ptr_zone')
