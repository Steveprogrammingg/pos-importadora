from models import db

class ProductBarcode(db.Model):
    __tablename__ = "product_barcodes"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    barcode = db.Column(db.String(80), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("company_id", "barcode", name="uq_company_barcode"),
        db.Index("ix_barcode_company", "company_id", "barcode"),
    )
