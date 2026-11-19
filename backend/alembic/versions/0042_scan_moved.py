"""scan_jobs.moved: songs a scan found under a new path (moved or renamed folders) and kept

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0042'
down_revision: str | None = '0041'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('scan_jobs', sa.Column('moved', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('scan_jobs', 'moved')
