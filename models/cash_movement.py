from datetime import datetime

from models import db


class CashMoveType:
    IN_ = "IN"   # Ingreso
    OUT = "OUT"  # Egreso

    ALL = {IN_, OUT}


class CashMovement(db.Model):
    __tablename__ = "cash_movements"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, nullable=False, index=True)
    branch_id = db.Column(db.Integer, nullable=False, index=True)

    move_date = db.Column(db.Date, nullable=False, index=True)
    move_type = db.Column(db.String(10), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
