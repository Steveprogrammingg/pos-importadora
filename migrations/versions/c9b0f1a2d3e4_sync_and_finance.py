"""sync events and finance tables

Revision ID: c9b0f1a2d3e4
Revises: b7c1d3a4f5e6
Create Date: 2026-01-28

"""

from alembic import op
import sqlalchemy as sa


revision = "c9b0f1a2d3e4"
down_revision = "b7c1d3a4f5e6"
branch_labels = None
depends_on = None


def upgrade():
    # ---- Sync events ----
    op.create_table(
        "sync_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("sync_events") as batch_op:
        batch_op.create_index(batch_op.f("ix_sync_events_company_id"), ["company_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_branch_id"), ["branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_entity"), ["entity"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_entity_id"), ["entity_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_sync_events_updated_at"), ["updated_at"], unique=False)

    # ---- Cash movements ----
    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("move_date", sa.Date(), nullable=False),
        sa.Column("move_type", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cash_movements") as batch_op:
        batch_op.create_index(batch_op.f("ix_cash_movements_company_id"), ["company_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_movements_branch_id"), ["branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_movements_move_date"), ["move_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_movements_move_type"), ["move_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_cash_movements_created_at"), ["created_at"], unique=False)

    # ---- Expenses ----
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=False, server_default="CASH"),
        sa.Column("vendor", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("receipt_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("expenses") as batch_op:
        batch_op.create_index(batch_op.f("ix_expenses_company_id"), ["company_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_expenses_branch_id"), ["branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_expenses_expense_date"), ["expense_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_expenses_category"), ["category"], unique=False)
        batch_op.create_index(batch_op.f("ix_expenses_created_at"), ["created_at"], unique=False)


def downgrade():
    op.drop_table("expenses")
    op.drop_table("cash_movements")
    op.drop_table("sync_events")
