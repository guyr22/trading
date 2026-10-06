"""Record user stock splits without rewriting trades

Revision ID: d3762534ca7a
Revises: e4f5a6b7c8d9
Create Date: 2026-10-06 15:07:36.330186

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3762534ca7a'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stock_splits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('new_shares', sa.Float(), nullable=False),
        sa.Column('old_shares', sa.Float(), nullable=False),
        sa.Column('executed_at', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('new_shares > 0 AND old_shares > 0 AND new_shares != old_shares', name='ck_stock_splits_ratio'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ticker', 'executed_at', name='uq_stock_splits_user_ticker_date'),
    )
    op.create_index('ix_stock_splits_user_ticker_date', 'stock_splits', ['user_id', 'ticker', 'executed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_stock_splits_user_ticker_date', table_name='stock_splits')
    op.drop_table('stock_splits')
