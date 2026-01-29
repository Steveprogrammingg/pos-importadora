from datetime import datetime

from flask import url_for

from . import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    name = db.Column(db.String(160), nullable=False)

    sku = db.Column(db.String(60), nullable=True)
    barcode = db.Column(db.String(60), nullable=True)

    price_minorista = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price_mayorista = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price_especial = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Precio de costo (para cálculo de ganancia)
    cost_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Imagen (opcional) para POS / Dashboard
    image_path = db.Column(db.String(255), nullable=True)
    image_updated_at = db.Column(db.DateTime, nullable=True)

    @property
    def image_url(self) -> str | None:
        """URL pública para mostrar la imagen en templates.

        - Se sirve desde /static/<image_path>
        - Usa un cache-buster con image_updated_at para que refresque al reemplazar.
        """
        if not self.image_path:
            return None
        base = url_for("static", filename=self.image_path)
        if self.image_updated_at:
            return f"{base}?v={int(self.image_updated_at.timestamp())}"
        return base

    __table_args__ = (
        db.UniqueConstraint("company_id", "sku", name="uq_product_company_sku"),
        db.UniqueConstraint("company_id", "barcode", name="uq_product_company_barcode"),
    )

    def __repr__(self):
        return f"<Product {self.id} {self.name} company={self.company_id}>"
