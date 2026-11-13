"""Lyrics an admin chose for a song (api/lyrics_admin.py, the file in DATA_DIR/lrc): kept, never
looked up again, ahead of the song's own; or none shown

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0036'
down_revision: str | None = '0035'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('fetched_lyrics', sa.Column('pinned', sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('fetched_lyrics', 'pinned')
