"""Indexes on the foreign keys that had none (deleting a song, a user or a chart looked through the
whole table for rows pointing at it), and artists.bio, never used

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0040'
down_revision: str | None = '0039'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    ('extract_jobs', 'user_id'),
    ('extract_jobs', 'track_id'),
    ('videos', 'added_by'),
    ('playlists', 'chart_id'),
)


def upgrade() -> None:
    for table, column in INDEXES:
        op.create_index(f'ix_{table}_{column}', table, [column])
    op.drop_column('artists', 'bio')


def downgrade() -> None:
    op.add_column('artists', sa.Column('bio', sa.Text(), nullable=True))
    for table, column in INDEXES:
        op.drop_index(f'ix_{table}_{column}', table_name=table)
