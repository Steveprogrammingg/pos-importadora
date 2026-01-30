from datetime import datetime

from models import db


class CashCount(db.Model):
    """Conteo de caja por día.

    Guarda el efectivo contado (físico) para comparar con el efectivo esperado.
    Un registro por (company_id, branch_id, count_date).
    """

    __tablename__ = "cash_counts"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, nullable=False, index=True)
    branch_id = db.Column(db.Integer, nullable=False, index=True)

    count_date = db.Column(db.Date, nullable=False, index=True)

    amount_counted = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint("company_id", "branch_id", "count_date", name="uq_cash_counts_day"),
    )
