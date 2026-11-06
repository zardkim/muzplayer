"""Album ratings on Melon (and likes on Bugs)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0028'
down_revision: str | None = '0027'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('albums', sa.Column('site_ratings', sa.JSON(), nullable=True))
    op.add_column('albums', sa.Column('site_ratings_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('albums', 'site_ratings_at')
    op.drop_column('albums', 'site_ratings')
