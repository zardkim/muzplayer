"""The default lists' Korean names follow the app's wording, 플레이리스트 → 재생목록 (only those
still named as they were made)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = '0037'
down_revision: str | None = '0036'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE playlists SET name = '기본 재생목록' WHERE is_default AND name = '기본 플레이리스트'")
    op.execute("UPDATE video_playlists SET name = '기본 영상 재생목록' WHERE is_default AND name = '기본 영상 플레이리스트'")


def downgrade() -> None:
    op.execute("UPDATE playlists SET name = '기본 플레이리스트' WHERE is_default AND name = '기본 재생목록'")
    op.execute("UPDATE video_playlists SET name = '기본 영상 플레이리스트' WHERE is_default AND name = '기본 영상 재생목록'")
