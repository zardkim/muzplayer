"""audio quality, soundtracks, release dates, home screen rows

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31
"""

import re
from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op


revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def full_date(text: str | None) -> date | None:
    m = re.match(r"(\d{4})[-./](\d{2})[-./](\d{2})", text or "")
    try:
        return date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


def upgrade() -> None:
    # read from each file's header by the next scan (NULL = not read yet)
    op.add_column('tracks', sa.Column('sample_rate', sa.Integer(), nullable=True))
    op.add_column('tracks', sa.Column('bit_depth', sa.SmallInteger(), nullable=True))
    op.add_column('tracks', sa.Column('bitrate', sa.Integer(), nullable=True))
    op.add_column('albums', sa.Column('quality', sa.String(length=16), nullable=True))
    op.add_column('albums', sa.Column('release_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('home_sections', sa.JSON(), nullable=True))
    # soundtracks are their own kind now: the next scan works the tag kinds out again
    op.execute('UPDATE tracks SET tag_kind = NULL')
    # full release dates from the tags already stored (date, else originaldate), earliest per
    # album; parsed here, not in SQL, so an impossible date (2011-02-30) is skipped, not an error
    bind = op.get_bind()
    rows = bind.execute(sa.text(r"""
        SELECT album_id, coalesce(tag_json->'date'->>0, tag_json->'originaldate'->>0)
        FROM tracks
        WHERE album_id IS NOT NULL
          AND coalesce(tag_json->'date'->>0, tag_json->'originaldate'->>0) ~ '^\d{4}[-./]\d{2}[-./]\d{2}'
    """))
    dates: dict[int, date] = {}
    for album_id, text in rows:
        d = full_date(text)
        if d and (album_id not in dates or d < dates[album_id]):
            dates[album_id] = d
    if dates:
        bind.execute(
            sa.text("UPDATE albums SET release_date = :d WHERE id = :id"),
            [{"id": k, "d": v} for k, v in dates.items()],
        )


def downgrade() -> None:
    op.drop_column('users', 'home_sections')
    op.drop_column('albums', 'release_date')
    op.drop_column('albums', 'quality')
    op.drop_column('tracks', 'bitrate')
    op.drop_column('tracks', 'bit_depth')
    op.drop_column('tracks', 'sample_rate')
