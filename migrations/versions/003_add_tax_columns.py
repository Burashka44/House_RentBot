"""add tax columns

Revision ID: 003_add_tax_columns
Revises: 002_add_missing_tables
Create Date: 2025-12-29 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_tax_columns'
down_revision: Union[str, None] = '002_add_missing_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add tax_rate to tenant_stays
    op.add_column('tenant_stays', sa.Column('tax_rate', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False))
    
    # 2. Add breakdown columns to rent_charges
    op.add_column('rent_charges', sa.Column('base_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('rent_charges', sa.Column('tax_amount', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False))
    op.add_column('rent_charges', sa.Column('tax_rate_snapshot', sa.Numeric(precision=5, scale=2), server_default='0', nullable=True))
    
    # For existing records, set base_amount = amount (assuming tax was 0 or included)
    # Using raw SQL for update is safest cross-platform, but Alembic execution is better
    op.execute("UPDATE rent_charges SET base_amount = amount")
    op.alter_column('rent_charges', 'base_amount', nullable=False)


def downgrade() -> None:
    op.drop_column('rent_charges', 'tax_rate_snapshot')
    op.drop_column('rent_charges', 'tax_amount')
    op.drop_column('rent_charges', 'base_amount')
    op.drop_column('tenant_stays', 'tax_rate')
