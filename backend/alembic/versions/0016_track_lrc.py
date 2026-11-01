"""Tracks: synced lyrics (LRC) in the tags or in a .lrc file next to them

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('tracks', sa.Column('lrc_tag', sa.Boolean(), nullable=True))
    op.add_column('tracks', sa.Column('lrc_file', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('tracks', 'lrc_file')
    op.drop_column('tracks', 'lrc_tag')
