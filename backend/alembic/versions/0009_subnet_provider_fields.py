"""subnet dns/dhcp provider name fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('subnets',
        sa.Column('dns_provider_name', sa.String(255), nullable=True))
    op.add_column('subnets',
        sa.Column('dhcp_provider_name', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('subnets', 'dns_provider_name')
    op.drop_column('subnets', 'dhcp_provider_name')
