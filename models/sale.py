from datetime import datetime
from . import db


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False, index=True)

    # Cliente (opcional)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)

    # Relación opcional (útil para ticket/reportes)
    client = db.relationship("Client", lazy="joined")

    # price_mode usado en la venta: minorista/mayorista/especial
    price_mode = db.Column(db.String(20), nullable=False, default="minorista")

    # Método de pago usado en la venta: cash/transfer
    payment_method = db.Column(db.String(20), nullable=False, default="cash")

    subtotal = db.Column(db.Numeric(14, 2), nullable=False, default="0.00")
    discount_total = db.Column(db.Numeric(14, 2), nullable=False, default="0.00")
    total = db.Column(db.Numeric(14, 2), nullable=False, default="0.00")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    items = db.relationship(
        "SaleItem",
        backref="sale",
        lazy="selectin",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.Index("ix_sales_company_created", "company_id", "created_at"),
        db.Index("ix_sales_company_branch_created", "company_id", "branch_id", "created_at"),
    )

    def __repr__(self):
        return f"<Sale {self.id} company={self.company_id} branch={self.branch_id} total={self.total}>"


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)

    # Relación para acceder: it.product.name / it.product.sku / it.product.barcode
    product = db.relationship("Product", lazy="joined")

    qty = db.Column(db.Numeric(14, 3), nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    # Costo unitario “fotografiado” al momento de vender (para reportes de ganancia).
    unit_cost = db.Column(db.Numeric(14, 2), nullable=False, default="0.00")
    discount = db.Column(db.Numeric(14, 2), nullable=False, default="0.00")
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)

    __table_args__ = (
        db.Index("ix_sale_items_sale_product", "sale_id", "product_id"),
    )

    def __repr__(self):
        return f"<SaleItem sale={self.sale_id} product={self.product_id} qty={self.qty}>"
