"""create stock transfers tables

Revision ID: f0c0stocktransfer06
Revises: f0c0cashcount03
Create Date: 2026-01-30

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0c0stocktransfer06'
down_revision = 'f0c0cashcount03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stock_transfers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('from_branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('to_branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_stock_transfers_company_date', 'stock_transfers', ['company_id', 'created_at'])

    op.create_table(
        'stock_transfer_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('stock_transfers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('qty', sa.Numeric(14, 3), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_stock_transfer_items_transfer', 'stock_transfer_items', ['transfer_id'])
    op.create_index('ix_stock_transfer_items_product', 'stock_transfer_items', ['product_id'])


def downgrade():
    op.drop_index('ix_stock_transfer_items_product', table_name='stock_transfer_items')
    op.drop_index('ix_stock_transfer_items_transfer', table_name='stock_transfer_items')
    op.drop_table('stock_transfer_items')

    op.drop_index('ix_stock_transfers_company_date', table_name='stock_transfers')
    op.drop_table('stock_transfers')
