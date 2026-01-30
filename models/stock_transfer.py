from datetime import datetime
from . import db


class StockTransfer(db.Model):
    __tablename__ = "stock_transfers"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    from_branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    to_branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    note = db.Column(db.String(255), nullable=True)

    # Estado del documento (nivel comercial)
    # - DRAFT: no afecta stock
    # - CONFIRMED: afecta stock + kardex
    status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship("StockTransferItem", backref="transfer", lazy=True, cascade="all, delete-orphan")


class StockTransferItem(db.Model):
    __tablename__ = "stock_transfer_items"

    id = db.Column(db.Integer, primary_key=True)

    transfer_id = db.Column(db.Integer, db.ForeignKey("stock_transfers.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    qty = db.Column(db.Numeric(14, 3), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
