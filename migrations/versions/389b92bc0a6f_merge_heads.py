"""merge_heads

Revision ID: 389b92bc0a6f
Revises: 002_uk_rso_system, 003_add_tax_columns
Create Date: 2026-01-09 02:02:25.563235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '389b92bc0a6f'
down_revision: Union[str, None] = '003_add_tax_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
