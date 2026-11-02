"""Users: when each was last seen (online on the admin page), and a log of sign-ins and admin changes

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0024'
down_revision: str | None = '0023'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'activity_log',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('username', sa.String(64), nullable=False, server_default=''),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('detail', sa.String(300), nullable=False, server_default=''),
        sa.Column('ip', sa.String(64), nullable=False, server_default=''),
    )
    op.create_index('ix_activity_log_at', 'activity_log', ['at'])
    op.create_index('ix_activity_log_user_id', 'activity_log', ['user_id'])


def downgrade() -> None:
    op.drop_table('activity_log')
    op.drop_column('users', 'last_seen_at')
