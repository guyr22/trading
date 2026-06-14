"""remove digest_opt_in column from users

Drops the column added by d3e4f5a6b7c8 now that the weekly portfolio digest
email feature has been removed entirely.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-14 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'digest_opt_in')


def downgrade() -> None:
    op.add_column('users', sa.Column('digest_opt_in', sa.Boolean(), nullable=False, server_default='false'))
