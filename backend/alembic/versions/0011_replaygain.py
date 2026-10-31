"""ReplayGain values for volume levelling

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEYS = [f"rg_{s}_{p}" for s in ("track", "album") for p in ("gain", "peak")]


def number(text: str | None) -> float | None:
    m = re.match(r"\s*([-+]?\d+(?:[.,]\d+)?)", text or "")
    return float(m[1].replace(",", ".")) if m else None


def upgrade() -> None:
    for key in KEYS:
        op.add_column('tracks', sa.Column(key, sa.Float(), nullable=True))
    # from the tags already stored (easy mode keeps them as replaygain_track_gain, ...)
    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT id, tag_json->'replaygain_track_gain'->>0, tag_json->'replaygain_track_peak'->>0,
               tag_json->'replaygain_album_gain'->>0, tag_json->'replaygain_album_peak'->>0
        FROM tracks
        WHERE tag_json IS NOT NULL
          AND (tag_json->'replaygain_track_gain' IS NOT NULL OR tag_json->'replaygain_album_gain' IS NOT NULL)
    """)).all()
    values = [{"id": r[0], **{k: number(v) for k, v in zip(KEYS, r[1:])}} for r in rows]
    if values:
        bind.execute(
            sa.text("UPDATE tracks SET " + ", ".join(f"{k} = :{k}" for k in KEYS) + " WHERE id = :id"), values
        )


def downgrade() -> None:
    for key in KEYS:
        op.drop_column('tracks', key)
