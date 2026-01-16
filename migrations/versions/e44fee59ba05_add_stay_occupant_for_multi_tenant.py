"""add_stay_occupant_for_multi_tenant

Revision ID: e44fee59ba05
Revises: b0a29e247eaf
Create Date: 2026-01-09 19:42:47.296645

"""
from typing import Sequence, Union
from datetime import date

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e44fee59ba05'
down_revision: Union[str, None] = 'b0a29e247eaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create stay_occupants table
    op.create_table('stay_occupants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stay_id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('joined_date', sa.DATE(), nullable=False),
    sa.Column('left_date', sa.DATE(), nullable=True),
    sa.Column('receive_rent_notifications', sa.Boolean(), nullable=False),
    sa.Column('receive_comm_notifications', sa.Boolean(), nullable=False),
    sa.Column('receive_meter_reminders', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stay_id', 'tenant_id', name='uq_stay_tenant')
    )
    
    # Data migration: Populate stay_occupants from existing tenant_stays
    # This creates a 'primary' occupant for each existing stay
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO stay_occupants (stay_id, tenant_id, role, joined_date, 
                                     receive_rent_notifications, receive_comm_notifications, receive_meter_reminders)
        SELECT id, tenant_id, 'primary', date_from, TRUE, TRUE, TRUE
        FROM tenant_stays
        WHERE tenant_id IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_table('stay_occupants')
