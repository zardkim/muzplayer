"""audiobooks and per-user listening position

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('books',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('folder_path', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=1000), nullable=False),
    sa.Column('subtitle', sa.String(length=1000), nullable=False),
    sa.Column('authors', sa.String(length=1000), nullable=False),
    sa.Column('narrators', sa.String(length=1000), nullable=False),
    sa.Column('series', sa.String(length=500), nullable=False),
    sa.Column('series_seq', sa.String(length=32), nullable=False),
    sa.Column('genres', sa.JSON(), nullable=False),
    sa.Column('published_year', sa.Integer(), nullable=True),
    sa.Column('publisher', sa.String(length=500), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('isbn', sa.String(length=32), nullable=False),
    sa.Column('asin', sa.String(length=32), nullable=False),
    sa.Column('language', sa.String(length=64), nullable=False),
    sa.Column('duration', sa.Float(), nullable=False),
    sa.Column('chapters', sa.JSON(), nullable=False),
    sa.Column('files', sa.JSON(), nullable=False),
    sa.Column('cover_sig', sa.String(length=1000), nullable=False),
    sa.Column('has_cover', sa.Boolean(), nullable=False),
    sa.Column('locked', sa.JSON(), nullable=False),
    sa.Column('abs_id', sa.String(length=64), nullable=True),
    sa.Column('missing_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('folder_path')
    )
    op.create_index(op.f('ix_books_missing_at'), 'books', ['missing_at'], unique=False)
    op.create_table('book_progress',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('book_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Float(), nullable=False),
    sa.Column('finished', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'book_id')
    )
    op.create_index(op.f('ix_book_progress_book_id'), 'book_progress', ['book_id'], unique=False)
    for column in ('books_added', 'books_updated', 'books_missing'):
        op.add_column('scan_jobs', sa.Column(column, sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    for column in ('books_missing', 'books_updated', 'books_added'):
        op.drop_column('scan_jobs', column)
    op.drop_index(op.f('ix_book_progress_book_id'), table_name='book_progress')
    op.drop_table('book_progress')
    op.drop_index(op.f('ix_books_missing_at'), table_name='books')
    op.drop_table('books')
