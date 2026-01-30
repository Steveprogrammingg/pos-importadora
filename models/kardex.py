from datetime import datetime
from . import db


class KardexMoveType:
    OPENING = "OPENING"          # inicial (opcional)
    PURCHASE_IN = "PURCHASE_IN"  # compra a bodega (entrada)
    TRANSFER = "TRANSFER"        # transferencias
    ADJUST = "ADJUST"            # ajuste manual
    SHRINKAGE = "SHRINKAGE"    # merma / faltante
    DAMAGE = "DAMAGE"          # daño / caducado
    SALE_OUT = "SALE_OUT"        # salida por venta
    SALE_EDIT = "SALE_EDIT"      # ajuste por edicion de venta
    SALE_VOID = "SALE_VOID"      # anulacion/borrado de venta


    ALL = {OPENING, PURCHASE_IN, TRANSFER, ADJUST, SHRINKAGE, DAMAGE, SALE_OUT, SALE_EDIT, SALE_VOID}


class KardexMovement(db.Model):
    """
    Kardex por producto, siempre registramos:
    - desde (from_) y hacia (to_) dependiendo del tipo
    - qty positivo (movimiento de cantidad)
    - unit_cost opcional (para costo promedio futuro)
    """
    __tablename__ = "kardex_movements"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)

    move_type = db.Column(db.String(20), nullable=False)  # KardexMoveType.*

    # Ubicación origen (puede ser None en compras/entradas)
    from_location_type = db.Column(db.String(20), nullable=True)   # WAREHOUSE/BRANCH
    from_location_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)

    # Ubicación destino (puede ser None en ventas/salidas)
    to_location_type = db.Column(db.String(20), nullable=True)     # WAREHOUSE/BRANCH
    to_location_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)

    qty = db.Column(db.Numeric(14, 3), nullable=False)  # siempre positivo
    unit_cost = db.Column(db.Numeric(14, 4), nullable=True)  # opcional para costos

    note = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_kardex_company_product_date", "company_id", "product_id", "created_at"),
        db.Index("ix_kardex_company_from", "company_id", "from_location_type", "from_location_id"),
        db.Index("ix_kardex_company_to", "company_id", "to_location_type", "to_location_id"),
    )

    def __repr__(self):
        return f"<KardexMovement {self.id} {self.move_type} product={self.product_id} qty={self.qty}>"
