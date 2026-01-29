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
    
    # Use raw SQL for SQLite compatibility with IF NOT EXISTS
    from sqlalchemy import text
    conn = op.get_bind()
    
    # Check if we're using SQLite
    is_sqlite = conn.dialect.name == 'sqlite'
    
    # Helper function to create index if not exists
    def create_index_safe(index_name, table_name, columns):
        # SQLite and PostgreSQL both support CREATE INDEX IF NOT EXISTS
        # We use raw SQL to ensure idempotency and avoid "relation already exists" errors
        cols = ', '.join(columns)
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({cols})'))
    
    # Tenants - tg_id used in authentication and lookups
    # create_index_safe('ix_tenants_tg_id', 'tenants', ['tg_id'])
    
    # Payments - stay_id and status used in queries
    create_index_safe('ix_payments_stay_id', 'payments', ['stay_id'])
    create_index_safe('ix_payments_status', 'payments', ['status'])
    
    # Rent charges - composite index for common query pattern
    create_index_safe('ix_rent_charges_stay_month', 'rent_charges', ['stay_id', 'month'])
    create_index_safe('ix_rent_charges_status', 'rent_charges', ['status'])
    
    # Comm charges - composite index for common query pattern
    create_index_safe('ix_comm_charges_stay_month', 'comm_charges', ['stay_id', 'month'])
    create_index_safe('ix_comm_charges_status', 'comm_charges', ['status'])
    
    # Payment allocations - foreign keys used in JOINs
    create_index_safe('ix_allocations_payment', 'payment_allocations', ['payment_id'])
    create_index_safe('ix_allocations_charge', 'payment_allocations', ['charge_id', 'charge_type'])
    
    # Tenant stays - object_id and status for filtering
    create_index_safe('ix_stays_object_status', 'tenant_stays', ['object_id', 'status'])
    create_index_safe('ix_stays_tenant', 'tenant_stays', ['tenant_id'])
    
    # Invite codes - code used in redemption
    create_index_safe('ix_invite_codes_code', 'invite_codes', ['code'])
    
    # Users - tg_id for authentication
    create_index_safe('ix_users_tg_id', 'users', ['tg_id'])


def downgrade() -> None:
    # Drop indexes in reverse order
    # Use IF EXISTS for safety
    from sqlalchemy import text
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == 'sqlite'
    
    def drop_index_safe(index_name, table_name=None):
        if is_sqlite:
            conn.execute(text(f'DROP INDEX IF EXISTS {index_name}'))
        else:
            op.drop_index(index_name, table_name=table_name)
    
    drop_index_safe('ix_users_tg_id', 'users')
    drop_index_safe('ix_invite_codes_code', 'invite_codes')
    drop_index_safe('ix_stays_tenant', 'tenant_stays')
    drop_index_safe('ix_stays_object_status', 'tenant_stays')
    drop_index_safe('ix_allocations_charge', 'payment_allocations')
    drop_index_safe('ix_allocations_payment', 'payment_allocations')
    drop_index_safe('ix_comm_charges_status', 'comm_charges')
    drop_index_safe('ix_comm_charges_stay_month', 'comm_charges')
    drop_index_safe('ix_rent_charges_status', 'rent_charges')
    drop_index_safe('ix_rent_charges_stay_month', 'rent_charges')
    drop_index_safe('ix_payments_status', 'payments')
    drop_index_safe('ix_payments_stay_id', 'payments')
    drop_index_safe('ix_tenants_tg_id', 'tenants')
