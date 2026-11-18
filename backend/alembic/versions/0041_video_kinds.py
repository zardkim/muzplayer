"""Music video kinds an admin can add, rename, order and remove (video_kinds), starting with the six
that were built in

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0041'
down_revision: str | None = '0040'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILT_IN = ('mv', 'concert', 'tv', 'fan', 'cover', 'other')


def upgrade() -> None:
    kinds = op.create_table(
        'video_kinds',
        sa.Column('key', sa.String(16), primary_key=True),
        sa.Column('name', sa.String(50), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
    )
    op.bulk_insert(kinds, [{'key': k, 'name': None, 'position': i} for i, k in enumerate(BUILT_IN)])


def downgrade() -> None:
    # videos of an added kind go back to "other"
    op.execute("update videos set kind = 'other' where kind not in ('mv', 'concert', 'tv', 'fan', 'cover', 'other')")
    op.drop_table('video_kinds')
