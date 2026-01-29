from datetime import datetime

from models import db


class SyncEventStatus:
    PENDING = "PENDING"
    SENT = "SENT"
    APPLIED = "APPLIED"
    ERROR = "ERROR"


class SyncEvent(db.Model):
    """Eventos offline-first.

    La idea: cada acción importante (venta, gasto, movimientos de inventario) genera
    un evento. Si hay internet, se "push" al servidor central. Si no, queda en cola.
    """

    __tablename__ = "sync_events"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, nullable=False, index=True)
    branch_id = db.Column(db.Integer, nullable=False, index=True)

    entity = db.Column(db.String(50), nullable=False, index=True)  # e.g., "SALE", "EXPENSE"
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    action = db.Column(db.String(20), nullable=False, index=True)  # e.g., "CREATE", "UPDATE"

    payload_json = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), nullable=False, default=SyncEventStatus.PENDING, index=True)
    last_error = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
