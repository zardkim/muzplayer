"""large libraries: search column and trigram indexes, cover versions, library version

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    op.add_column('tracks', sa.Column('search_text', sa.Text(), server_default='', nullable=False))
    op.execute(
        "UPDATE tracks t SET search_text = lower(t.title || ' ' || t.artist_text || ' ' || coalesce(a.title, '')) "
        "FROM albums a WHERE a.id = t.album_id"
    )
    op.execute("UPDATE tracks SET search_text = lower(title || ' ' || artist_text) WHERE album_id IS NULL")
    op.execute('CREATE INDEX ix_tracks_search_text ON tracks USING gin (search_text gin_trgm_ops)')
    op.execute('CREATE INDEX ix_albums_title_trgm ON albums USING gin (title gin_trgm_ops)')
    op.execute('CREATE INDEX ix_artists_name_trgm ON artists USING gin (name gin_trgm_ops)')
    op.create_index('ix_albums_album_artist_id', 'albums', ['album_artist_id'])
    # the song list's default order: the first page without sorting every song
    op.execute('CREATE INDEX ix_tracks_title_lower ON tracks (lower(title), id)')

    # covers made before this version: their source is unknown, so the next scan remakes them once
    op.add_column('albums', sa.Column('cover_version', sa.Integer(), server_default='0', nullable=False))
    op.add_column('albums', sa.Column('cover_source', sa.Text(), nullable=True))
    op.add_column('albums', sa.Column('cover_mtime', sa.Float(), nullable=True))
    op.execute('UPDATE albums SET cover_version = 1 WHERE cover_path IS NOT NULL')
    op.add_column('books', sa.Column('cover_version', sa.Integer(), server_default='0', nullable=False))
    op.execute('UPDATE books SET cover_version = 1 WHERE has_cover')

    op.create_table('library_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.BigInteger(), server_default='1', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.execute('INSERT INTO library_state (id, version) VALUES (1, 1)')


def downgrade() -> None:
    op.drop_table('library_state')
    op.drop_column('books', 'cover_version')
    op.drop_column('albums', 'cover_mtime')
    op.drop_column('albums', 'cover_source')
    op.drop_column('albums', 'cover_version')
    op.execute('DROP INDEX ix_tracks_title_lower')
    op.drop_index('ix_albums_album_artist_id', table_name='albums')
    op.execute('DROP INDEX ix_artists_name_trgm')
    op.execute('DROP INDEX ix_albums_title_trgm')
    op.execute('DROP INDEX ix_tracks_search_text')
    op.drop_column('tracks', 'search_text')
