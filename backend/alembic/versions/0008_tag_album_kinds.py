"""album kind from tags (compilation, 비정규)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL until the next scan works it out from the stored tags (and refiles the songs)
    op.add_column('tracks', sa.Column('tag_kind', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('tracks', 'tag_kind')
