"""create cash_counts

Revision ID: f0c0cashcount03
Revises: f0c0addpaymeth02
Create Date: 2026-01-30

"""

from alembic import op
import sqlalchemy as sa


revision = 'f0c0cashcount03'
down_revision = 'f0c0addpaymeth02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cash_counts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=False),
        sa.Column('count_date', sa.Date(), nullable=False),
        sa.Column('amount_counted', sa.Numeric(12, 2), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'branch_id', 'count_date', name='uq_cash_counts_day'),
    )
    op.create_index('ix_cash_counts_company_id', 'cash_counts', ['company_id'], unique=False)
    op.create_index('ix_cash_counts_branch_id', 'cash_counts', ['branch_id'], unique=False)
    op.create_index('ix_cash_counts_count_date', 'cash_counts', ['count_date'], unique=False)


def downgrade():
    op.drop_index('ix_cash_counts_count_date', table_name='cash_counts')
    op.drop_index('ix_cash_counts_branch_id', table_name='cash_counts')
    op.drop_index('ix_cash_counts_company_id', table_name='cash_counts')
    op.drop_table('cash_counts')
