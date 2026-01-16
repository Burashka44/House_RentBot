"""add_constraints_and_cascades

Revision ID: b0a29e247eaf
Revises: 2c60826df4c3
Create Date: 2026-01-09 19:17:23.448394

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0a29e247eaf'
down_revision: Union[str, None] = '2c60826df4c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add UNIQUE constraints only
    # Note: CASCADE deletes are defined in models.py but SQLite doesn't support
    # altering FK constraints. For existing databases, CASCADE will only apply
    # to new records. For full CASCADE support, recreate database from scratch.
    
    with op.batch_alter_table('object_rso_links', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_object_rso', ['object_id', 'provider_id'])
    
    with op.batch_alter_table('uk_rso_links', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_uk_rso', ['uk_id', 'provider_id'])


def downgrade() -> None:
    with op.batch_alter_table('uk_rso_links', schema=None) as batch_op:
        batch_op.drop_constraint('uq_uk_rso', type_='unique')
    
    with op.batch_alter_table('object_rso_links', schema=None) as batch_op:
        batch_op.drop_constraint('uq_object_rso', type_='unique')
