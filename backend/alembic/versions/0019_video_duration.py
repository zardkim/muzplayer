"""Videos: the length of a NAS file (read with its thumbnail)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('duration', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('videos', 'duration')
