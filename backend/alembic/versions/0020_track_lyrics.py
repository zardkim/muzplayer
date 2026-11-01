"""Tracks: lyrics in the tags now counts plain lyrics too; songs found without synced ones are looked at again

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-01
"""

from collections.abc import Sequence

from alembic import op


revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # lrc_tag was "synced lyrics in the tags"; now "any lyrics": the next scan reads those tags again
    op.execute("UPDATE tracks SET lrc_tag = NULL WHERE lrc_tag IS FALSE")


def downgrade() -> None:
    pass
