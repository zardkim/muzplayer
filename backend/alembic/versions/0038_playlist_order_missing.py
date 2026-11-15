"""Playlists in their owner's own order (playlists.sort_order), and the entries of an imported
playlist file not found in the library, kept to be looked for again (playlist_missing)

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0038'
down_revision: str | None = '0037'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('playlists', sa.Column('sort_order', sa.Integer, nullable=True))
    op.create_table(
        'playlist_missing',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('playlist_id', sa.Integer, sa.ForeignKey('playlists.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer, nullable=False),
        sa.Column('path', sa.Text, nullable=False),
        sa.Column('label', sa.Text, nullable=False, server_default=''),
        sa.Column('duration', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_playlist_missing_playlist_id', 'playlist_missing', ['playlist_id'])


def downgrade() -> None:
    op.drop_index('ix_playlist_missing_playlist_id', 'playlist_missing')
    op.drop_table('playlist_missing')
    op.drop_column('playlists', 'sort_order')
