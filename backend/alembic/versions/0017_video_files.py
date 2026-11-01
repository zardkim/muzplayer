"""Music videos: files on the NAS beside YouTube videos; kinds mv, concert, tv, fan, other

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('file_path', sa.String(1000), nullable=True))
    op.alter_column('videos', 'youtube_id', existing_type=sa.String(16), nullable=True)
    op.drop_constraint('ck_videos_target', 'videos', type_='check')
    op.create_check_constraint(
        'ck_videos_source', 'videos',
        "(youtube_id IS NOT NULL AND file_path IS NULL AND num_nonnulls(album_id, track_id) = 1)"
        " OR (file_path IS NOT NULL AND youtube_id IS NULL AND num_nonnulls(album_id, track_id) <= 1)",
    )
    op.create_unique_constraint('videos_file_path_key', 'videos', ['file_path'])
    # the new kinds: live -> concert; covers by others -> fan videos
    op.execute("UPDATE videos SET kind = 'concert' WHERE kind = 'live'")
    op.execute("UPDATE videos SET kind = 'fan' WHERE kind = 'cover'")


def downgrade() -> None:
    op.execute("DELETE FROM videos WHERE file_path IS NOT NULL")
    op.execute("UPDATE videos SET kind = 'live' WHERE kind = 'concert'")
    op.execute("UPDATE videos SET kind = 'cover' WHERE kind = 'fan'")
    op.execute("UPDATE videos SET kind = 'other' WHERE kind = 'tv'")
    op.drop_constraint('videos_file_path_key', 'videos', type_='unique')
    op.drop_constraint('ck_videos_source', 'videos', type_='check')
    op.create_check_constraint('ck_videos_target', 'videos', 'num_nonnulls(album_id, track_id) = 1')
    op.alter_column('videos', 'youtube_id', existing_type=sa.String(16), nullable=False)
    op.drop_column('videos', 'file_path')
