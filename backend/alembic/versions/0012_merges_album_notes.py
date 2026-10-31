"""Merged artist/genre names; album descriptions

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'name_aliases',
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('target', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('kind', 'name'),
    )
    op.add_column('albums', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('albums', sa.Column('description_source', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('albums', 'description_source')
    op.drop_column('albums', 'description')
    op.drop_table('name_aliases')
