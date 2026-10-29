"""album kinds, top-level folder kinds, charts

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29

Existing rows become kind "album"; the first scan after the upgrade reclassifies
tracks by folder (see scanner), so no data migration is needed here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('library_folders',
    sa.Column('path', sa.String(length=500), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('path')
    )
    op.create_table('charts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('folder_path', sa.Text(), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('folder_path')
    )

    op.add_column('albums', sa.Column('kind', sa.String(length=16), server_default='album', nullable=False))
    op.drop_constraint('albums_album_artist_id_title_key', 'albums', type_='unique')
    op.create_unique_constraint(
        'albums_kind_album_artist_id_title_key', 'albums', ['kind', 'album_artist_id', 'title'],
        postgresql_nulls_not_distinct=True,
    )

    op.add_column('tracks', sa.Column('chart_id', sa.Integer(), nullable=True))
    op.add_column('tracks', sa.Column('chart_position', sa.Integer(), nullable=True))
    op.add_column('tracks', sa.Column('canonical_track_id', sa.Integer(), nullable=True))
    op.create_foreign_key('tracks_chart_id_fkey', 'tracks', 'charts', ['chart_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(
        'tracks_canonical_track_id_fkey', 'tracks', 'tracks', ['canonical_track_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index(op.f('ix_tracks_chart_id'), 'tracks', ['chart_id'], unique=False)
    op.create_index(op.f('ix_tracks_canonical_track_id'), 'tracks', ['canonical_track_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tracks_canonical_track_id'), table_name='tracks')
    op.drop_index(op.f('ix_tracks_chart_id'), table_name='tracks')
    op.drop_constraint('tracks_canonical_track_id_fkey', 'tracks', type_='foreignkey')
    op.drop_constraint('tracks_chart_id_fkey', 'tracks', type_='foreignkey')
    op.drop_column('tracks', 'canonical_track_id')
    op.drop_column('tracks', 'chart_position')
    op.drop_column('tracks', 'chart_id')
    # drops empty non-album albums; if an album and its chart copy both still hold tracks the
    # old constraint can't be restored and this fails: restore the 0.2 backup instead
    op.execute("DELETE FROM albums WHERE kind <> 'album' AND id NOT IN (SELECT album_id FROM tracks WHERE album_id IS NOT NULL)")
    op.drop_constraint('albums_kind_album_artist_id_title_key', 'albums', type_='unique')
    op.drop_column('albums', 'kind')
    op.create_unique_constraint(
        'albums_album_artist_id_title_key', 'albums', ['album_artist_id', 'title'],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_table('charts')
    op.drop_table('library_folders')
