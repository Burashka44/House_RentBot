"""add uk and rso system

Revision ID: 002_uk_rso_system
Revises: 001_initial
Create Date: 2024-05-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_uk_rso_system'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # UK Companies
    op.create_table('uk_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('inn', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uk_companies_inn'), 'uk_companies', ['inn'], unique=True)

    # Houses
    op.create_table('houses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=False),
        sa.Column('street', sa.String(), nullable=False),
        sa.Column('house_number', sa.String(), nullable=False),
        sa.Column('uk_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['uk_id'], ['uk_companies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_houses_city'), 'houses', ['city'], unique=False)
    op.create_index(op.f('ix_houses_street'), 'houses', ['street'], unique=False)

    # UK RSO Links
    op.create_table('uk_rso_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uk_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.ForeignKeyConstraint(['uk_id'], ['uk_companies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uk_id', 'provider_id', name='uq_uk_provider')
    )

    # Object RSO Links
    op.create_table('object_rso_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['object_id'], ['objects.id'], ),
        sa.ForeignKeyConstraint(['provider_id'], ['comm_providers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('object_id', 'provider_id', name='uq_object_provider')
    )


def downgrade() -> None:
    op.drop_table('object_rso_links')
    op.drop_table('uk_rso_links')
    op.drop_index(op.f('ix_houses_street'), table_name='houses')
    op.drop_index(op.f('ix_houses_city'), table_name='houses')
    op.drop_table('houses')
    op.drop_index(op.f('ix_uk_companies_inn'), table_name='uk_companies')
    op.drop_table('uk_companies')
