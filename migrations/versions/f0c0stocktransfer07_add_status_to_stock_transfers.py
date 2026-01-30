"""add status/confirmed_at to stock transfers

Revision ID: f0c0stocktransfer07
Revises: f0c0stocktransfer06
Create Date: 2026-01-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# --- Alembic identifiers (OBLIGATORIO) ---
revision = "f0c0stocktransfer07"
down_revision = "f0c0stocktransfer06"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    insp = inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("stock_transfers")}

    # Agrega columnas solo si no existen (por si corrió a medias antes)
    if "status" not in existing_cols:
        op.add_column(
            "stock_transfers",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        )

    if "confirmed_at" not in existing_cols:
        op.add_column(
            "stock_transfers",
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        )

    # SQLite no soporta DROP DEFAULT en ALTER COLUMN
    if dialect != "sqlite":
        op.alter_column("stock_transfers", "status", server_default=None)


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("stock_transfers")}

    if "confirmed_at" in existing_cols:
        op.drop_column("stock_transfers", "confirmed_at")
    if "status" in existing_cols:
        op.drop_column("stock_transfers", "status")
