"""add_performance_indexes

Revision ID: 2b6dbae4ab2d
Revises: 3013bcb190fa
Create Date: 2026-01-19 23:28:33.191190

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b6dbae4ab2d'
down_revision: Union[str, None] = '3013bcb190fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Critical indexes for performance
    # These columns are used in WHERE clauses and JOINs frequently
    
    # Tenants - tg_id used in authentication and lookups
    op.create_index('ix_tenants_tg_id', 'tenants', ['tg_id'], unique=False)
    
    # Payments - stay_id and status used in queries
    op.create_index('ix_payments_stay_id', 'payments', ['stay_id'], unique=False)
    op.create_index('ix_payments_status', 'payments', ['status'], unique=False)
    
    # Rent charges - composite index for common query pattern
    op.create_index('ix_rent_charges_stay_month', 'rent_charges', ['stay_id', 'month'], unique=False)
    op.create_index('ix_rent_charges_status', 'rent_charges', ['status'], unique=False)
    
    # Comm charges - composite index for common query pattern
    op.create_index('ix_comm_charges_stay_month', 'comm_charges', ['stay_id', 'month'], unique=False)
    op.create_index('ix_comm_charges_status', 'comm_charges', ['status'], unique=False)
    
    # Payment allocations - foreign keys used in JOINs
    op.create_index('ix_allocations_payment', 'payment_allocations', ['payment_id'], unique=False)
    op.create_index('ix_allocations_charge', 'payment_allocations', ['charge_id', 'charge_type'], unique=False)
    
    # Tenant stays - object_id and status for filtering
    op.create_index('ix_stays_object_status', 'tenant_stays', ['object_id', 'status'], unique=False)
    op.create_index('ix_stays_tenant', 'tenant_stays', ['tenant_id'], unique=False)
    
    # Invite codes - code used in redemption
    op.create_index('ix_invite_codes_code', 'invite_codes', ['code'], unique=False)
    
    # Users - tg_id for authentication
    op.create_index('ix_users_tg_id', 'users', ['tg_id'], unique=False)


def downgrade() -> None:
    # Drop indexes in reverse order
    op.drop_index('ix_users_tg_id', table_name='users')
    op.drop_index('ix_invite_codes_code', table_name='invite_codes')
    op.drop_index('ix_stays_tenant', table_name='tenant_stays')
    op.drop_index('ix_stays_object_status', table_name='tenant_stays')
    op.drop_index('ix_allocations_charge', table_name='payment_allocations')
    op.drop_index('ix_allocations_payment', table_name='payment_allocations')
    op.drop_index('ix_comm_charges_status', table_name='comm_charges')
    op.drop_index('ix_comm_charges_stay_month', table_name='comm_charges')
    op.drop_index('ix_rent_charges_status', table_name='rent_charges')
    op.drop_index('ix_rent_charges_stay_month', table_name='rent_charges')
    op.drop_index('ix_payments_status', table_name='payments')
    op.drop_index('ix_payments_stay_id', table_name='payments')
    op.drop_index('ix_tenants_tg_id', table_name='tenants')
