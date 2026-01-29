from datetime import datetime

from models import db


class ExpenseCategory:
    RENT = "RENT"
    SALARIES = "SALARIES"
    UTILITIES = "UTILITIES"
    SUPPLIES = "SUPPLIES"
    TRANSPORT = "TRANSPORT"
    MAINTENANCE = "MAINTENANCE"
    TAXES = "TAXES"
    MARKETING = "MARKETING"
    OTHER = "OTHER"

    ALL = {
        RENT,
        SALARIES,
        UTILITIES,
        SUPPLIES,
        TRANSPORT,
        MAINTENANCE,
        TAXES,
        MARKETING,
        OTHER,
    }


class PaymentMethod:
    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    OTHER = "OTHER"

    ALL = {CASH, CARD, TRANSFER, OTHER}


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, nullable=False, index=True)
    branch_id = db.Column(db.Integer, nullable=False, index=True)

    expense_date = db.Column(db.Date, nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    payment_method = db.Column(db.String(20), nullable=False, default=PaymentMethod.CASH)
    vendor = db.Column(db.String(120), nullable=True)
    note = db.Column(db.Text, nullable=True)

    # comprobante (ruta en static/uploads o URL)
    receipt_path = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)