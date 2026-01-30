"""merge heads (product barcodes + sales indexes)

Revision ID: f0c0mergeheads01
Revises: b7c1d3a4f5e6, d50816482485
Create Date: 2026-01-30 21:00:02

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f0c0mergeheads01'
down_revision = ('b7c1d3a4f5e6', 'd50816482485')
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration: no schema changes
    pass


def downgrade():
    # Downgrade merge: no schema changes
    pass
