"""Playlists: shared ones (made from a chart or theme, shown to everyone) and the chart each came from

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0025'
down_revision: str | None = '0024'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('playlists', sa.Column('is_shared', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('playlists', sa.Column('chart_id', sa.Integer(), sa.ForeignKey('charts.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_playlists_is_shared', 'playlists', ['is_shared'])


def downgrade() -> None:
    op.drop_index('ix_playlists_is_shared', 'playlists')
    op.drop_column('playlists', 'chart_id')
    op.drop_column('playlists', 'is_shared')
