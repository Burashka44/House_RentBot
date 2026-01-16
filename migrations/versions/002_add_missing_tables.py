"""add missing tables

Revision ID: 002_add_missing_tables
Revises: 001_initial
Create Date: 2025-12-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_missing_tables'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. UK Companies
    op.create_table('uk_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('inn', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uk_companies_inn'), 'uk_companies', ['inn'], unique=True)

    # 2. Houses
    op.create_table('houses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=False),
        sa.Column('street', sa.String(), nullable=False),
        sa.Column('house_number', sa.String(), nullable=False),
        sa.Column('uk_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['uk_id'], ['uk_companies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_houses_city'), 'houses', ['city'], unique=False)
    op.create_index(op.f('ix_houses_street'), 'houses', ['street'], unique=False)

    # 3. UK-RSO Links
    op.create_table('uk_rso_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uk_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.ForeignKeyConstraint(['uk_id'], ['uk_companies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. Object-RSO Links
    op.create_table('object_rso_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 5. Users (Admins/Owners)
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tg_id', sa.BigInteger(), nullable=False),
        sa.Column('tg_username', sa.String(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_tg_id'), 'users', ['tg_id'], unique=True)

    # 6. Tenant Settings
    op.create_table('tenant_settings',
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=False),
        sa.Column('rent_notifications', sa.Boolean(), nullable=False),
        sa.Column('comm_notifications', sa.Boolean(), nullable=False),
        sa.Column('reminder_days', sa.Integer(), nullable=False),
        sa.Column('reminder_count', sa.Integer(), nullable=False),
        sa.Column('preferred_time', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('tenant_id')
    )

    # 7. Service Subscriptions
    op.create_table('service_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stay_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('account_number', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.ForeignKeyConstraint(['stay_id'], ['tenant_stays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 8. Invite Codes
    op.create_table('invite_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('object_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_used', sa.Boolean(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invite_codes_code'), 'invite_codes', ['code'], unique=True)

    # 9. Admin Contacts
    op.create_table('admin_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('telegram', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('admin_contacts')
    op.drop_index(op.f('ix_invite_codes_code'), table_name='invite_codes')
    op.drop_table('invite_codes')
    op.drop_table('service_subscriptions')
    op.drop_table('tenant_settings')
    op.drop_index(op.f('ix_users_tg_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('object_rso_links')
    op.drop_table('uk_rso_links')
    op.drop_index(op.f('ix_houses_street'), table_name='houses')
    op.drop_index(op.f('ix_houses_city'), table_name='houses')
    op.drop_table('houses')
    op.drop_index(op.f('ix_uk_companies_inn'), table_name='uk_companies')
    op.drop_table('uk_companies')
