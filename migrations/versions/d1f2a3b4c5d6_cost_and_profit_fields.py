"""add cost_price to products and unit_cost to sale_items

Revision ID: d1f2a3b4c5d6
Revises: c9b0f1a2d3e4
Create Date: 2026-01-29

"""

from alembic import op
import sqlalchemy as sa


revision = "d1f2a3b4c5d6"
down_revision = "c9b0f1a2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    """Add cost fields used for profit calculation."""

    # SQLite-friendly migrations using batch_alter_table.
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(
            sa.Column("cost_price", sa.Numeric(12, 2), nullable=False, server_default="0")
        )

    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.add_column(
            sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False, server_default="0.00")
        )


def downgrade():
    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.drop_column("unit_cost")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("cost_price")
