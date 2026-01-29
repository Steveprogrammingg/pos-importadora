from datetime import datetime
from . import db


class LocationType:
    WAREHOUSE = "WAREHOUSE"
    BRANCH = "BRANCH"
    ALL = {WAREHOUSE, BRANCH}


class Inventory(db.Model):
    """
    Stock por producto y ubicación.
    location_type:
      - WAREHOUSE: la bodega central (Branch con is_warehouse=True)
      - BRANCH: una sucursal normal
    location_id:
      - siempre es Branch.id (tanto bodega como sucursal)
    """
    __tablename__ = "inventories"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    location_type = db.Column(db.String(20), nullable=False)  # WAREHOUSE / BRANCH
    location_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    qty = db.Column(db.Numeric(14, 3), nullable=False, default=0)  # soporta unidad/peso

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "product_id", "location_type", "location_id",
            name="uq_inventory_company_product_location"
        ),
        db.Index("ix_inventory_company_location", "company_id", "location_type", "location_id"),
    )

    def __repr__(self):
        return f"<Inventory company={self.company_id} product={self.product_id} {self.location_type}:{self.location_id} qty={self.qty}>"
