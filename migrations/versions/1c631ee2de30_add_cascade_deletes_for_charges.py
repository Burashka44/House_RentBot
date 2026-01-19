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
    # Add CASCADE delete for charges
    # When a stay is deleted, all associated charges should be deleted automatically
    
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
