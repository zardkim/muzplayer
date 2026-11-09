"""Every artist of a song (feat., collaborations), and artists sorted across scripts

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0032'
down_revision: str | None = '0031'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'track_artists',
        sa.Column('track_id', sa.Integer(), sa.ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('artist_id', sa.Integer(), sa.ForeignKey('artists.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('position', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('role', sa.String(8), nullable=False, server_default='main'),
    )
    op.create_index('ix_track_artists_artist_id', 'track_artists', ['artist_id'])
    op.add_column('artists', sa.Column('sort_own', sa.String(500), nullable=False, server_default=''))
    op.add_column('library_state', sa.Column('links_version', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('library_state', 'links_version')
    op.drop_column('artists', 'sort_own')
    op.drop_index('ix_track_artists_artist_id', 'track_artists')
    op.drop_table('track_artists')
