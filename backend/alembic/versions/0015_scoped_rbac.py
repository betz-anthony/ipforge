"""scoped rbac: groups and subnet grants

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(64), nullable=False, unique=True),
        sa.Column('description', sa.String(255), nullable=True),
    )
    op.create_table(
        'user_group_members',
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('group_id', sa.Integer(),
                  sa.ForeignKey('user_groups.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'subnet_grants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('group_id', sa.Integer(),
                  sa.ForeignKey('user_groups.id', ondelete='CASCADE'), nullable=True),
        sa.Column('subnet_id', sa.Integer(),
                  sa.ForeignKey('subnets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permission', sa.String(16), nullable=False),
    )
    op.create_index('ix_subnet_grants_user_id', 'subnet_grants', ['user_id'])
    op.create_index('ix_subnet_grants_group_id', 'subnet_grants', ['group_id'])
    op.create_index('ix_subnet_grants_subnet_id', 'subnet_grants', ['subnet_id'])


def downgrade() -> None:
    op.drop_index('ix_subnet_grants_subnet_id', table_name='subnet_grants')
    op.drop_index('ix_subnet_grants_group_id', table_name='subnet_grants')
    op.drop_index('ix_subnet_grants_user_id', table_name='subnet_grants')
    op.drop_table('subnet_grants')
    op.drop_table('user_group_members')
    op.drop_table('user_groups')
