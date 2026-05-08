"""add scan_results and collisions tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE addressstatus ADD VALUE IF NOT EXISTS 'discovered'")

    op.create_table(
        'scan_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subnet_id', sa.Integer(), sa.ForeignKey('subnets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip_address', sa.String(50), nullable=False),
        sa.Column('reachable', sa.Boolean(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('scanned_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_scan_results_subnet_scanned', 'scan_results', ['subnet_id', 'scanned_at'])
    op.create_index('ix_scan_results_ip', 'scan_results', ['ip_address'])

    op.create_table(
        'collisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ip_address', sa.String(50), nullable=False),
        sa.Column('collision_type', sa.String(50), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('ip_address', 'collision_type', name='uq_collision_ip_type'),
    )
    op.create_index('ix_collisions_ip', 'collisions', ['ip_address'])


def downgrade() -> None:
    # NOTE: PostgreSQL does not support ALTER TYPE ... DROP VALUE, so the
    # 'discovered' value added to addressstatus cannot be removed here.
    # It is intentionally left in place.
    op.drop_index('ix_collisions_ip', 'collisions')
    op.drop_table('collisions')
    op.drop_index('ix_scan_results_ip', 'scan_results')
    op.drop_index('ix_scan_results_subnet_scanned', 'scan_results')
    op.drop_table('scan_results')
