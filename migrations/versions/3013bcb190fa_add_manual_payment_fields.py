"""add_manual_payment_fields

Revision ID: 3013bcb190fa
Revises: e7a246c1d10c
Create Date: 2026-01-16 02:26:03.647297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3013bcb190fa'
down_revision: Union[str, None] = 'e7a246c1d10c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add manual payment tracking fields
    op.add_column('payments', sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('payments', sa.Column('marked_by', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    # Remove manual payment tracking fields
    op.drop_column('payments', 'marked_by')
    op.drop_column('payments', 'is_manual')
