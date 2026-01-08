"""initial

Revision ID: 001_initial
Revises: 
Create Date: 2024-05-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.create_table('tenants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tg_id', sa.BigInteger(), nullable=False),
        sa.Column('tg_username', sa.String(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('passport_data', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('active', 'archived', 'banned', 'privacy_revoked', name='tenantstatus'), nullable=False),
        sa.Column('personal_data_consent', sa.Boolean(), nullable=False),
        sa.Column('consent_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consent_version', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_tg_id'), 'tenants', ['tg_id'], unique=True)

    # Objects
    op.create_table('objects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('free', 'occupied', 'repair', name='objectstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Object Settings
    op.create_table('object_settings',
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('comm_bill_day', sa.Integer(), nullable=False),
        sa.Column('min_ready_ratio', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('max_comm_reminders', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.PrimaryKeyConstraint('object_id')
    )

    # Tenant Stays
    op.create_table('tenant_stays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('date_from', sa.DATE(), nullable=False),
        sa.Column('date_to', sa.DATE(), nullable=True),
        sa.Column('rent_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('rent_day', sa.Integer(), nullable=False),
        sa.Column('comm_day', sa.Integer(), nullable=False),
        sa.Column('notifications_mode', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('active', 'archived', name='staystatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Comm Providers
    op.create_table('comm_providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('service_type', sa.Enum('electric', 'water', 'heating', 'garbage', 'internet', 'tv', 'phone', 'other', name='commservicetype'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('short_keywords', sa.JSON(), nullable=False),
        sa.Column('account_number', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Rent Charges
    op.create_table('rent_charges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.DATE(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('status', sa.Enum('pending', 'paid', name='chargestatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Comm Charges
    op.create_table('comm_charges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('service_type', sa.Enum('electric', 'water', 'heating', 'garbage', 'internet', 'tv', 'phone', 'other', name='commservicetype'), nullable=False),
        sa.Column('month', sa.DATE(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('status', sa.Enum('pending', 'paid', name='chargestatus'), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Payments
    op.create_table('payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum('rent', 'comm', name='paymenttype'), nullable=False),
        sa.Column('rent_charge_id', sa.Integer(), nullable=True),
        sa.Column('comm_charge_id', sa.Integer(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('pending_manual', 'confirmed', 'auto_confirmed', 'rejected', name='paymentstatus'), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['comm_charge_id'], ['comm_charges.id'], ),
        sa.ForeignKeyConstraint(['rent_charge_id'], ['rent_charges.id'], ),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Payment Receipts
    op.create_table('payment_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.Column('ocr_text', sa.Text(), nullable=True),
        sa.Column('ocr_conf', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('parsed_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('parsed_date', sa.DATE(), nullable=True),
        sa.Column('parsed_receiver', sa.String(), nullable=True),
        sa.Column('parsed_purpose', sa.String(), nullable=True),
        sa.Column('parsed_raw_json', sa.JSON(), nullable=True),
        sa.Column('decision', sa.Enum('accepted', 'rejected', name='receiptdecision'), nullable=False),
        sa.Column('reject_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_id')
    )

    # Rent Receivers
    op.create_table('rent_receivers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=False),
        sa.Column('tg_username', sa.String(), nullable=True),
        sa.Column('card_last4', sa.String(), nullable=True),
        sa.Column('card_bank', sa.String(), nullable=True),
        sa.Column('yoomoney_acc', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Support Messages
    op.create_table('support_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('from_role', sa.Enum('tenant', 'admin', name='role'), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('is_read_by_admin', sa.Boolean(), nullable=False),
        sa.Column('is_read_by_tenant', sa.Boolean(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Support Attachments
    op.create_table('support_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('file_type', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['support_messages.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('support_attachments')
    op.drop_table('support_messages')
    op.drop_table('rent_receivers')
    op.drop_table('payment_receipts')
    op.drop_table('payments')
    op.drop_table('comm_charges')
    op.drop_table('rent_charges')
    op.drop_table('comm_providers')
    op.drop_table('tenant_stays')
    op.drop_table('object_settings')
    op.drop_table('objects')
    op.drop_index(op.f('ix_tenants_tg_id'), table_name='tenants')
    op.drop_table('tenants')
