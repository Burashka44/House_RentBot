"""merge_migration_branches

Revision ID: a99f41ae61d0
Revises: 0141b0d6b487, add_payment_details_rso
Create Date: 2026-01-12 20:10:25.500264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a99f41ae61d0'
down_revision: Union[str, None] = ('0141b0d6b487', 'add_payment_details_rso')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
