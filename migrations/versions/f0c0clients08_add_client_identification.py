"""add client identification type/number

Revision ID: f0c0clients08
Revises: f0c0stocktransfer07
Create Date: 2026-01-30
"""

from alembic import op
import sqlalchemy as sa

revision = "f0c0clients08"
down_revision = "f0c0stocktransfer07"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clients") as batch_op:
        batch_op.add_column(sa.Column("identification_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("identification_number", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_clients_company_idnum", ["company_id", "identification_number"])


def downgrade():
    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_index("ix_clients_company_idnum")
        batch_op.drop_column("identification_number")
        batch_op.drop_column("identification_type")
