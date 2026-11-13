"""Audio taken out of music videos (extract.py): one job a video, its state and the file made

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0035'
down_revision: str | None = '0034'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'extract_jobs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('video_id', sa.Integer, sa.ForeignKey('videos.id', ondelete='SET NULL'), index=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('format', sa.String(8), nullable=False, server_default='m4a'),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('step', sa.String(16), nullable=False, server_default=''),
        sa.Column('progress', sa.Float, nullable=False, server_default='0'),
        sa.Column('error', sa.String(200)),
        sa.Column('title', sa.String(500), nullable=False, server_default=''),
        sa.Column('found', sa.JSON),
        sa.Column('file_path', sa.Text),
        sa.Column('track_id', sa.Integer, sa.ForeignKey('tracks.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table('extract_jobs')
