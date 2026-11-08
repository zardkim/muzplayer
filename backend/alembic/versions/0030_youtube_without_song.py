"""YouTube videos added from the Music videos page by their link, with no song or album

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0030'
down_revision: str | None = '0029'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('ck_videos_source', 'videos', type_='check')
    op.create_check_constraint(
        'ck_videos_source', 'videos',
        "num_nonnulls(youtube_id, file_path) = 1 AND num_nonnulls(album_id, track_id) <= 1",
    )
    # one of each YouTube video on its own (with a song or album, once per song or album as before)
    op.create_index(
        'ux_videos_youtube_alone', 'videos', ['youtube_id'], unique=True,
        postgresql_where=sa.text('youtube_id IS NOT NULL AND album_id IS NULL AND track_id IS NULL'),
    )


def downgrade() -> None:
    op.execute("DELETE FROM videos WHERE youtube_id IS NOT NULL AND album_id IS NULL AND track_id IS NULL")
    op.drop_index('ux_videos_youtube_alone', 'videos')
    op.drop_constraint('ck_videos_source', 'videos', type_='check')
    op.create_check_constraint(
        'ck_videos_source', 'videos',
        "(youtube_id IS NOT NULL AND file_path IS NULL AND num_nonnulls(album_id, track_id) = 1)"
        " OR (file_path IS NOT NULL AND youtube_id IS NULL AND num_nonnulls(album_id, track_id) <= 1)",
    )
