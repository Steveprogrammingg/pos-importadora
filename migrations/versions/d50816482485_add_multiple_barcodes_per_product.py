"""add multiple barcodes per product

Revision ID: d50816482485
Revises: d1f2a3b4c5d6
Create Date: 2026-01-29 16:25:52.809488

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd50816482485'
down_revision = 'd1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_barcodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(length=80), nullable=False),

        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE"
        ),

        sa.UniqueConstraint(
            "company_id",
            "barcode",
            name="uq_company_barcode"
        )
    )

    op.create_index(
        "ix_product_barcodes_company_barcode",
        "product_barcodes",
        ["company_id", "barcode"]
    )


def downgrade():
    op.drop_index(
        "ix_product_barcodes_company_barcode",
        table_name="product_barcodes"
    )
    op.drop_table("product_barcodes")

