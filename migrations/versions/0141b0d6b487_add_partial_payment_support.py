"""add_partial_payment_support

Revision ID: 0141b0d6b487
Revises: e44fee59ba05
Create Date: 2026-01-09 20:12:58.948725

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0141b0d6b487'
down_revision: Union[str, None] = 'e44fee59ba05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create payment_allocations table
    op.create_table('payment_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('charge_id', sa.Integer(), nullable=False),
    sa.Column('charge_type', sa.String(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Add new columns to payments table using batch mode
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True))
        batch_op.add_column(sa.Column('allocated_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('unallocated_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('unallocated_amount')
        batch_op.drop_column('allocated_amount')
        batch_op.drop_column('total_amount')
    
    op.drop_table('payment_allocations')
