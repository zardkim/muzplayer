"""Search index for albums and artists; its version

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # filled by search_index.rebuild at the next start (songs' text is rebuilt then too)
    for table in ('albums', 'artists'):
        op.add_column(table, sa.Column('search_text', sa.Text(), server_default='', nullable=False))
        op.create_index(
            f'ix_{table}_search_text', table, ['search_text'],
            postgresql_using='gin', postgresql_ops={'search_text': 'gin_trgm_ops'},
        )
    op.add_column('library_state', sa.Column('search_version', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('library_state', 'search_version')
    for table in ('albums', 'artists'):
        op.drop_index(f'ix_{table}_search_text', table_name=table)
        op.drop_column(table, 'search_text')
