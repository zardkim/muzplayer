"""users.taste: what a user told the smart playlist wizard they like (smart.Taste); smart_snapshots:
a smart playlist's songs kept for a day or a week (rules.refresh), so its random picks stay put

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0043'
down_revision: str | None = '0042'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('taste', sa.JSON(), nullable=True))
    op.create_table(
        'smart_snapshots',
        sa.Column('playlist_id', sa.Integer(), sa.ForeignKey('playlists.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('track_ids', sa.JSON(), nullable=False),
        sa.Column('made_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('smart_snapshots')
    op.drop_column('users', 'taste')
