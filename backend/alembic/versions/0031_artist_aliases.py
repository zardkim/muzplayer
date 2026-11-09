"""Artists' other names (머라이어 캐리 for Mariah Carey), looked up or added by hand

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0031'
down_revision: str | None = '0030'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('artists', sa.Column('aliases', sa.JSON(), nullable=True))
    op.add_column('artists', sa.Column('aliases_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('artists', 'aliases_checked_at')
    op.drop_column('artists', 'aliases')
