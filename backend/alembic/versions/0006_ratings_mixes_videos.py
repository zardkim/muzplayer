"""ratings, liked albums, play counts, smart playlists, YouTube videos

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('track_ratings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_track_ratings_rating'),
    sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'track_id')
    )
    op.create_index('ix_track_ratings_track_id', 'track_ratings', ['track_id'])
    op.create_table('album_ratings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('album_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_album_ratings_rating'),
    sa.ForeignKeyConstraint(['album_id'], ['albums.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'album_id')
    )
    op.create_index('ix_album_ratings_album_id', 'album_ratings', ['album_id'])
    op.create_table('album_favorites',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('album_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['album_id'], ['albums.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'album_id')
    )
    op.create_index('ix_album_favorites_album_id', 'album_favorites', ['album_id'])

    op.create_table('play_counts',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('plays', sa.Integer(), nullable=False),
    sa.Column('last_played_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'track_id')
    )
    op.create_index('ix_play_counts_track_id', 'play_counts', ['track_id'])
    op.create_index('ix_play_counts_user_plays', 'play_counts', ['user_id', 'plays'])
    op.create_index('ix_play_counts_user_last', 'play_counts', ['user_id', 'last_played_at'])
    # start from the plays still in the history (it keeps each user's latest 1,000)
    op.execute(
        'INSERT INTO play_counts (user_id, track_id, plays, last_played_at) '
        'SELECT user_id, track_id, count(*), max(played_at) FROM play_history GROUP BY user_id, track_id'
    )

    op.add_column('playlists', sa.Column('kind', sa.String(length=16), server_default='manual', nullable=False))
    op.add_column('playlists', sa.Column('rules', sa.JSON(), nullable=True))

    op.create_table('videos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('album_id', sa.Integer(), nullable=True),
    sa.Column('track_id', sa.Integer(), nullable=True),
    sa.Column('youtube_id', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('channel', sa.String(length=200), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('added_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('num_nonnulls(album_id, track_id) = 1', name='ck_videos_target'),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['album_id'], ['albums.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('album_id', 'youtube_id'),
    sa.UniqueConstraint('track_id', 'youtube_id')
    )
    op.create_index('ix_videos_album_id', 'videos', ['album_id'])
    op.create_index('ix_videos_track_id', 'videos', ['track_id'])
    # "recently added" mixes and lists
    op.create_index('ix_tracks_created_at', 'tracks', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_tracks_created_at', table_name='tracks')
    op.drop_table('videos')
    op.drop_column('playlists', 'rules')
    op.drop_column('playlists', 'kind')
    op.drop_table('play_counts')
    op.drop_table('album_favorites')
    op.drop_table('album_ratings')
    op.drop_table('track_ratings')
