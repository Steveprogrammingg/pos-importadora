"""add product images

Revision ID: b7c1d3a4f5e6
Revises: e1a32dc06825
Create Date: 2026-01-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d3a4f5e6'
down_revision = 'e1a32dc06825'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    def _has_column(table_name: str, col_name: str) -> bool:
        rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(r[1] == col_name for r in rows)

    with op.batch_alter_table('products', schema=None) as batch_op:
        # Algunas DB ya traen image_path por una migración anterior.
        if not _has_column('products', 'image_path'):
            batch_op.add_column(sa.Column('image_path', sa.String(length=255), nullable=True))
        if not _has_column('products', 'image_updated_at'):
            batch_op.add_column(sa.Column('image_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    # En SQLite, remover columnas puede romper instalaciones existentes.
    pass
