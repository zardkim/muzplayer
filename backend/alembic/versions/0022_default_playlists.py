"""Each person's default playlist and default video playlist

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0022'
down_revision: str | None = '0021'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ('playlists', 'video_playlists'):
        op.add_column(table, sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False))
        # one default each (made on first use, also when two requests come at once)
        op.create_index(f'uq_{table}_default', table, ['user_id'], unique=True, postgresql_where=sa.text('is_default'))


def downgrade() -> None:
    for table in ('playlists', 'video_playlists'):
        op.drop_index(f'uq_{table}_default', table_name=table)
        op.drop_column(table, 'is_default')
