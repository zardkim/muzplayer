"""half-star ratings, per-user "record history" setting

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ratings are kept in half stars from now on: 4 stars -> 8
    for table in ('track_ratings', 'album_ratings'):
        op.drop_constraint(f'ck_{table}_rating', table, type_='check')
        op.execute(f'UPDATE {table} SET rating = rating * 2')
        op.create_check_constraint(f'ck_{table}_rating', table, 'rating BETWEEN 1 AND 10')
    op.add_column('users', sa.Column('record_history', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'record_history')
    for table in ('track_ratings', 'album_ratings'):
        op.drop_constraint(f'ck_{table}_rating', table, type_='check')
        op.execute(f'UPDATE {table} SET rating = GREATEST(1, ROUND(rating / 2.0))')
        op.create_check_constraint(f'ck_{table}_rating', table, 'rating BETWEEN 1 AND 5')
