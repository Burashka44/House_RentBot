"""add_cascade_deletes_for_charges

Revision ID: 1c631ee2de30
Revises: 2b6dbae4ab2d
Create Date: 2026-01-19 23:40:06.147322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c631ee2de30'
down_revision: Union[str, None] = '2b6dbae4ab2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite doesn't support ALTER CONSTRAINT
    # For SQLite, we need to use batch mode or skip this migration
    # For PostgreSQL, we can alter constraints
    
    from sqlalchemy import text
    conn = op.get_bind()
    
    # Check dialect
    if conn.dialect.name == 'sqlite':
        # SQLite: Skip constraint modification
        # Constraints will be created correctly in new tables
        # Existing tables will work with default RESTRICT
        print("SQLite detected: Skipping CASCADE constraint modification")
        print("Note: New tables will have CASCADE, existing tables use RESTRICT")
        return
    
    # PostgreSQL: Modify constraints
    # RentCharge.stay_id → CASCADE
    op.drop_constraint('rent_charges_stay_id_fkey', 'rent_charges', type_='foreignkey')
    op.create_foreign_key(
        'rent_charges_stay_id_fkey',
        'rent_charges', 'tenant_stays',
        ['stay_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # CommCharge.stay_id → CASCADE
    op.drop_constraint('comm_charges_stay_id_fkey', 'comm_charges', type_='foreignkey')
    op.create_foreign_key(
        'comm_charges_stay_id_fkey',
        'comm_charges', 'tenant_stays',
        ['stay_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Revert to default RESTRICT behavior
    from sqlalchemy import text
    conn = op.get_bind()
    
    if conn.dialect.name == 'sqlite':
        print("SQLite detected: Skipping constraint revert")
        return
    
    # RentCharge.stay_id → RESTRICT (default)
    op.drop_constraint('rent_charges_stay_id_fkey', 'rent_charges', type_='foreignkey')
    op.create_foreign_key(
        'rent_charges_stay_id_fkey',
        'rent_charges', 'tenant_stays',
        ['stay_id'], ['id']
    )
    
    # CommCharge.stay_id → RESTRICT (default)
    op.drop_constraint('comm_charges_stay_id_fkey', 'comm_charges', type_='foreignkey')
    op.create_foreign_key(
        'comm_charges_stay_id_fkey',
        'comm_charges', 'tenant_stays',
        ['stay_id'], ['id']
    )
