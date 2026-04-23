"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'subnets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('cidr', sa.String(50), nullable=False, unique=True),
        sa.Column('ip_version', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('vlan_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_subnets_cidr', 'subnets', ['cidr'])

    op.create_table(
        'ip_addresses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('address', sa.String(50), nullable=False, unique=True),
        sa.Column('subnet_id', sa.Integer(), sa.ForeignKey('subnets.id'), nullable=False),
        sa.Column('hostname', sa.String(255), nullable=True),
        sa.Column('status', sa.Enum('available', 'reserved', 'assigned', 'deprecated', name='addressstatus'), nullable=False, server_default='available'),
        sa.Column('mac_address', sa.String(17), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_ip_addresses_address', 'ip_addresses', ['address'])

    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', sa.String(), nullable=False, server_default=''),
    )

    op.create_table(
        'cache_dns_zones',
        sa.Column('zone', sa.String(), primary_key=True),
        sa.Column('source', sa.String(), primary_key=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
    )

    op.create_table(
        'cache_dns_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('record_type', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('zone', sa.String(), nullable=False),
        sa.Column('ttl', sa.Integer(), server_default='3600'),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cache_dns_records_zone', 'cache_dns_records', ['zone'])
    op.create_index('ix_cache_dns_records_source', 'cache_dns_records', ['source'])

    op.create_table(
        'cache_dhcp_scopes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), server_default=''),
        sa.Column('subnet_mask', sa.String(), server_default=''),
        sa.Column('start_range', sa.String(), server_default=''),
        sa.Column('end_range', sa.String(), server_default=''),
        sa.Column('description', sa.String(), server_default=''),
        sa.Column('active', sa.Boolean(), server_default='true'),
        sa.Column('ip_version', sa.Integer(), server_default='4'),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cache_dhcp_scopes_source', 'cache_dhcp_scopes', ['source'])

    op.create_table(
        'cache_dhcp_leases',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scope_id', sa.String(), nullable=False),
        sa.Column('ip_address', sa.String(), nullable=False),
        sa.Column('mac_address', sa.String(), server_default=''),
        sa.Column('client_duid', sa.String(), server_default=''),
        sa.Column('iaid', sa.Integer(), server_default='0'),
        sa.Column('name', sa.String(), server_default=''),
        sa.Column('description', sa.String(), server_default=''),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_cache_dhcp_leases_scope_id', 'cache_dhcp_leases', ['scope_id'])

    op.create_table(
        'sync_status',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), server_default='never'),
        sa.Column('error', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('sync_status')
    op.drop_table('cache_dhcp_leases')
    op.drop_table('cache_dhcp_scopes')
    op.drop_table('cache_dns_records')
    op.drop_table('cache_dns_zones')
    op.drop_table('app_settings')
    op.drop_table('ip_addresses')
    op.drop_index('ix_subnets_cidr', 'subnets')
    op.drop_table('subnets')
    op.execute('DROP TYPE IF EXISTS addressstatus')
