"""
Migration: Add payment details to RSO models
Adds fields for YooMoney/QIWI/SberPay integration

Fields added:
- CommProvider: inn, bik, bank_account, payment_purpose_template
- ObjectRSOLink: personal_account, contract_number, service_code

Generated: 2026-01-10
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_payment_details_rso'
down_revision = 'a99f41ae61d0'  # Merge migration that includes UK/RSO system
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add columns to comm_providers
    op.add_column('comm_providers', sa.Column('inn', sa.String(), nullable=True))
    op.add_column('comm_providers', sa.Column('bik', sa.String(), nullable=True))
    op.add_column('comm_providers', sa.Column('bank_account', sa.String(), nullable=True))
    op.add_column('comm_providers', sa.Column('payment_purpose_template', sa.Text(), nullable=True))
    op.add_column('comm_providers', sa.Column('yoomoney_service_id', sa.String(), nullable=True))
    
    # Add columns to object_rso_links
    op.add_column('object_rso_links', sa.Column('personal_account', sa.String(), nullable=True))
    op.add_column('object_rso_links', sa.Column('contract_number', sa.String(), nullable=True))
    op.add_column('object_rso_links', sa.Column('service_code', sa.String(), nullable=True))
    op.add_column('object_rso_links', sa.Column('payment_data', sa.JSON(), nullable=True))
    
    # Rename existing account_number to personal_account (if needed)
    # op.alter_column('object_rso_links', 'account_number', new_column_name='personal_account')


def downgrade() -> None:
    # Remove columns from comm_providers
    op.drop_column('comm_providers', 'yoomoney_service_id')
    op.drop_column('comm_providers', 'payment_purpose_template')
    op.drop_column('comm_providers', 'bank_account')
    op.drop_column('comm_providers', 'bik')
    op.drop_column('comm_providers', 'inn')
    
    # Remove columns from object_rso_links
    op.drop_column('object_rso_links', 'payment_data')
    op.drop_column('object_rso_links', 'service_code')
    op.drop_column('object_rso_links', 'contract_number')
    op.drop_column('object_rso_links', 'personal_account')
