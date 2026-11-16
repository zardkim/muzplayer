"""An extraction job's album to go into (extract_jobs.target): an extracted album of the same
singer, its art kept or made anew from its songs' covers, and maybe a new name for it

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0039'
down_revision: str | None = '0038'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('extract_jobs', sa.Column('target', sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column('extract_jobs', 'target')
