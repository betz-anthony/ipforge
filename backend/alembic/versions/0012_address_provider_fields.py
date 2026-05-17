"""add provider tracking fields to ip_addresses

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ip_addresses', sa.Column('dns_provider',  sa.String(255), nullable=True))
    op.add_column('ip_addresses', sa.Column('dns_zone',      sa.String(255), nullable=True))
    op.add_column('ip_addresses', sa.Column('dhcp_provider', sa.String(255), nullable=True))
    op.add_column('ip_addresses', sa.Column('dhcp_scope_id', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('ip_addresses', 'dns_provider')
    op.drop_column('ip_addresses', 'dns_zone')
    op.drop_column('ip_addresses', 'dhcp_provider')
    op.drop_column('ip_addresses', 'dhcp_scope_id')
