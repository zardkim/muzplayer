"""Artists linked to Bugs: its name, solo or group, members and groups

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0033'
down_revision: str | None = '0032'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('artists', sa.Column('bugs_id', sa.Integer(), nullable=True))
    op.create_index('ix_artists_bugs_id', 'artists', ['bugs_id'])
    op.add_column('artists', sa.Column('display_name', sa.String(500), nullable=True))
    op.add_column('artists', sa.Column('bugs_source', sa.String(16), nullable=True))
    op.add_column('artists', sa.Column('bugs_checked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('artists', sa.Column('info', sa.JSON(), nullable=True))
    op.add_column('albums', sa.Column('bugs_artists_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('albums', 'bugs_artists_at')
    op.drop_column('artists', 'info')
    op.drop_column('artists', 'bugs_checked_at')
    op.drop_column('artists', 'bugs_source')
    op.drop_column('artists', 'display_name')
    op.drop_index('ix_artists_bugs_id', 'artists')
    op.drop_column('artists', 'bugs_id')
