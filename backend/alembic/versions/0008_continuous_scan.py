"""continuous scan: history, alerts, scan interval, last seen

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('subnets',
        sa.Column('scan_interval_minutes', sa.Integer(), nullable=True))

    op.add_column('ip_addresses',
        sa.Column('last_seen', sa.DateTime(), nullable=True))

    op.create_table(
        'scan_history_daily',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(50), nullable=False),
        sa.Column('subnet_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('up_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_latency_ms', sa.Float(), nullable=True),
        sa.Column('uptime_pct', sa.Float(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['subnet_id'], ['subnets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip_address', 'date', name='uq_scan_history_ip_date'),
    )
    op.create_index('ix_scan_history_daily_ip_address', 'scan_history_daily', ['ip_address'])
    op.create_index('ix_scan_history_daily_subnet_id',  'scan_history_daily', ['subnet_id'])

    op.create_table(
        'alert_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('ip_address', sa.String(50), nullable=False),
        sa.Column('subnet_id', sa.Integer(), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['subnet_id'], ['subnets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alert_events_ip_address',   'alert_events', ['ip_address'])
    op.create_index('ix_alert_events_subnet_id',    'alert_events', ['subnet_id'])
    op.create_index('ix_alert_events_acknowledged', 'alert_events', ['acknowledged'])


def downgrade():
    op.drop_table('alert_events')
    op.drop_table('scan_history_daily')
    op.drop_column('ip_addresses', 'last_seen')
    op.drop_column('subnets', 'scan_interval_minutes')
