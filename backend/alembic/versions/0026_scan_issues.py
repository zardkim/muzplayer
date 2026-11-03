"""Scan problems kept until the next scan of their place (admin → library), and each song's own

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0026'
down_revision: str | None = '0025'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'scan_issues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('path', sa.Text(), nullable=False, unique=True),
        sa.Column('message', sa.Text(), nullable=False, server_default=''),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column('tracks', sa.Column('scan_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tracks', 'scan_error')
    op.drop_table('scan_issues')
