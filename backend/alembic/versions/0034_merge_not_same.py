"""Pairs of names an admin said are not the same (no more merge suggestions for them)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0034'
down_revision: str | None = '0033'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'merge_not_same',
        sa.Column('kind', sa.String(16), primary_key=True),
        sa.Column('a', sa.String(500), primary_key=True),
        sa.Column('b', sa.String(500), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('merge_not_same')
