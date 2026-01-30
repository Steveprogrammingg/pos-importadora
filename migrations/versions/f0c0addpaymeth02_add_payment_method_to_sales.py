"""add payment_method to sales

Revision ID: f0c0addpaymeth02
Revises: f0c0mergeheads01
Create Date: 2026-01-30 21:00:02

"""
from alembic import op
import sqlalchemy as sa

revision = 'f0c0addpaymeth02'
down_revision = 'f0c0mergeheads01'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_method', sa.String(length=20), nullable=False, server_default='cash'))
        batch_op.create_index('ix_sales_payment_method', ['payment_method'], unique=False)


def downgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_index('ix_sales_payment_method')
        batch_op.drop_column('payment_method')
