"""add auth tables and user_id columns

Revision ID: a1b2c3d4e5f6
Revises: e920117ef5cf
Create Date: 2026-05-15 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e920117ef5cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('used_by_id', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['used_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invites_id'), 'invites', ['id'], unique=False)
    op.create_index(op.f('ix_invites_token'), 'invites', ['token'], unique=True)

    op.add_column('trades', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_trades_user_id', 'trades', 'users', ['user_id'], ['id'])
    op.create_index('ix_trades_user_id', 'trades', ['user_id'], unique=False)
    op.create_index('ix_trades_user_id_date_id', 'trades', ['user_id', 'executed_at', 'id'], unique=False)

    op.add_column('index_trades', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_index_trades_user_id', 'index_trades', 'users', ['user_id'], ['id'])
    op.create_index('ix_index_trades_user_id', 'index_trades', ['user_id'], unique=False)
    op.create_index('ix_index_trades_user_id_date_id', 'index_trades', ['user_id', 'executed_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_index_trades_user_id_date_id', table_name='index_trades')
    op.drop_index('ix_index_trades_user_id', table_name='index_trades')
    op.drop_constraint('fk_index_trades_user_id', 'index_trades', type_='foreignkey')
    op.drop_column('index_trades', 'user_id')

    op.drop_index('ix_trades_user_id_date_id', table_name='trades')
    op.drop_index('ix_trades_user_id', table_name='trades')
    op.drop_constraint('fk_trades_user_id', 'trades', type_='foreignkey')
    op.drop_column('trades', 'user_id')

    op.drop_index(op.f('ix_invites_token'), table_name='invites')
    op.drop_index(op.f('ix_invites_id'), table_name='invites')
    op.drop_table('invites')

    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
