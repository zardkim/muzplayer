"""per-folder scans (scan, rescan, reset), artist photos

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL folder = the whole library
    op.add_column('scan_jobs', sa.Column('folder', sa.Text(), nullable=True))
    op.add_column('scan_jobs', sa.Column('mode', sa.String(length=8), server_default='scan', nullable=False))
    # artists.image_path (unused until now) holds where the photo came from: folder:<rel> | deezer:<id> | none
    op.add_column('artists', sa.Column('image_version', sa.Integer(), server_default='0', nullable=False))
    op.add_column('artists', sa.Column('image_checked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('artists', 'image_checked_at')
    op.drop_column('artists', 'image_version')
    op.drop_column('scan_jobs', 'mode')
    op.drop_column('scan_jobs', 'folder')
