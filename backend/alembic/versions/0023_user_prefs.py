"""Users: the app's settings kept on the server (the same on every device)

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0023'
down_revision: str | None = '0022'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('prefs', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'prefs')
