"""Lyrics fetched for songs without their own

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'fetched_lyrics',
        sa.Column('track_id', sa.Integer(), sa.ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('lrc', sa.Text(), nullable=True),
        sa.Column('source', sa.String(32), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('fetched_lyrics')
