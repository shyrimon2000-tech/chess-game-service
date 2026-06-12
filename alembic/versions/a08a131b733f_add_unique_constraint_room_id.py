"""add_unique_constraint_room_id

Revision ID: a08a131b733f
Revises: 979f0c89f290
Create Date: 2026-06-12 03:17:41.787173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a08a131b733f'
down_revision: Union[str, Sequence[str], None] = '979f0c89f290'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_games_room_id", "games", ["room_id"])


def downgrade() -> None:
    op.drop_constraint("uq_games_room_id", "games", type_="unique")
