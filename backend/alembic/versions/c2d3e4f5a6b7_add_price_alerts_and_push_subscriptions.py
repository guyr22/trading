"""add price_alerts and push_subscriptions tables

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'price_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('condition', sa.Enum('ABOVE', 'BELOW', name='alertcondition'), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_price', sa.Float(), nullable=True),
        sa.Column('triggered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_price_alerts_id'), 'price_alerts', ['id'], unique=False)
    op.create_index(op.f('ix_price_alerts_user_id'), 'price_alerts', ['user_id'], unique=False)
    op.create_index(op.f('ix_price_alerts_ticker'), 'price_alerts', ['ticker'], unique=False)
    op.create_index('ix_price_alerts_user_active', 'price_alerts', ['user_id', 'active'], unique=False)

    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=False),
        sa.Column('p256dh', sa.String(), nullable=False),
        sa.Column('auth', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint', name='uq_push_subscriptions_endpoint'),
    )
    op.create_index(op.f('ix_push_subscriptions_id'), 'push_subscriptions', ['id'], unique=False)
    op.create_index('ix_push_subs_user', 'push_subscriptions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_push_subs_user', table_name='push_subscriptions')
    op.drop_index(op.f('ix_push_subscriptions_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')

    op.drop_index('ix_price_alerts_user_active', table_name='price_alerts')
    op.drop_index(op.f('ix_price_alerts_ticker'), table_name='price_alerts')
    op.drop_index(op.f('ix_price_alerts_user_id'), table_name='price_alerts')
    op.drop_index(op.f('ix_price_alerts_id'), table_name='price_alerts')
    op.drop_table('price_alerts')
    sa.Enum(name='alertcondition').drop(op.get_bind(), checkfirst=True)
