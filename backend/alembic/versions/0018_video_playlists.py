"""Video playlists

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'video_playlists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_video_playlists_user_id', 'video_playlists', ['user_id'])
    op.create_table(
        'video_playlist_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('playlist_id', sa.Integer(), sa.ForeignKey('video_playlists.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_id', sa.Integer(), sa.ForeignKey('videos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_video_playlist_items_playlist_id', 'video_playlist_items', ['playlist_id'])
    op.create_index('ix_video_playlist_items_video_id', 'video_playlist_items', ['video_id'])


def downgrade() -> None:
    op.drop_table('video_playlist_items')
    op.drop_table('video_playlists')
