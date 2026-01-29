from datetime import datetime
from . import db


class ClientType:
    NORMAL = "NORMAL"
    MAYORISTA = "MAYORISTA"
    ESPECIAL = "ESPECIAL"

    ALL = {NORMAL, MAYORISTA, ESPECIAL}


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    full_name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(180), nullable=True)

    client_type = db.Column(db.String(20), nullable=False, default=ClientType.NORMAL)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_clients_company_name", "company_id", "full_name"),
    )

    @property
    def price_mode(self) -> str:
        """
        Convierte tipo de cliente a modo de precio del POS.
        NORMAL    -> minorista
        MAYORISTA -> mayorista
        ESPECIAL  -> especial
        """
        if self.client_type == ClientType.MAYORISTA:
            return "mayorista"
        if self.client_type == ClientType.ESPECIAL:
            return "especial"
        return "minorista"

    def __repr__(self):
        return f"<Client {self.id} {self.full_name} company={self.company_id}>"
