from decimal import Decimal, InvalidOperation
from typing import Optional
from sqlalchemy.orm import Session

from models.inventory import Inventory, LocationType
from models.kardex import KardexMovement, KardexMoveType


def _to_qty(val) -> Decimal:
    """
    Soporta cantidades con coma/punto. Devuelve Decimal(14,3) >= 0.
    """
    if val is None:
        return Decimal("0")
    s = str(val).strip().replace(",", ".")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    if d < 0:
        return Decimal("0")
    return d.quantize(Decimal("0.001"))


def get_or_create_inventory(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    location_type: str,
    location_id: int
) -> Inventory:
    inv = (
        db.query(Inventory)
        .filter_by(
            company_id=company_id,
            product_id=product_id,
            location_type=location_type,
            location_id=location_id,
        )
        .first()
    )
    if not inv:
        inv = Inventory(
            company_id=company_id,
            product_id=product_id,
            location_type=location_type,
            location_id=location_id,
            qty=Decimal("0.000"),
        )
        db.add(inv)
        db.flush()
    return inv


def add_stock(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    location_type: str,
    location_id: int,
    qty,
    move_type: str,
    note: Optional[str] = None,
    unit_cost=None
):
    """
    Suma stock en una ubicación (entrada/ajuste+).
    Registra kardex: from_=None -> to_=ubicación
    """
    if location_type not in LocationType.ALL:
        raise ValueError("location_type inválido")

    if move_type not in KardexMoveType.ALL:
        raise ValueError("move_type inválido")

    q = _to_qty(qty)
    if q <= 0:
        raise ValueError("qty debe ser > 0")

    inv = get_or_create_inventory(
        db,
        company_id=company_id,
        product_id=product_id,
        location_type=location_type,
        location_id=location_id,
    )

    inv.qty = _to_qty(inv.qty) + q

    km = KardexMovement(
        company_id=company_id,
        product_id=product_id,
        move_type=move_type,
        from_location_type=None,
        from_location_id=None,
        to_location_type=location_type,
        to_location_id=location_id,
        qty=q,
        unit_cost=_to_qty(unit_cost).quantize(Decimal("0.0001")) if unit_cost is not None else None,
        note=note,
    )
    db.add(km)
    db.flush()
    return inv, km


def remove_stock(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    location_type: str,
    location_id: int,
    qty,
    move_type: str,
    note: Optional[str] = None
):
    """
    Resta stock en una ubicación (venta/ajuste-/transferencia salida).
    Registra kardex: from_=ubicación -> to_=None
    """
    if location_type not in LocationType.ALL:
        raise ValueError("location_type inválido")

    if move_type not in KardexMoveType.ALL:
        raise ValueError("move_type inválido")

    q = _to_qty(qty)
    if q <= 0:
        raise ValueError("qty debe ser > 0")

    inv = get_or_create_inventory(
        db,
        company_id=company_id,
        product_id=product_id,
        location_type=location_type,
        location_id=location_id,
    )

    current = _to_qty(inv.qty)
    if current < q:
        raise ValueError(f"Stock insuficiente. Disponible={current} requerido={q}")

    inv.qty = current - q

    km = KardexMovement(
        company_id=company_id,
        product_id=product_id,
        move_type=move_type,
        from_location_type=location_type,
        from_location_id=location_id,
        to_location_type=None,
        to_location_id=None,
        qty=q,
        note=note,
    )
    db.add(km)
    db.flush()
    return inv, km


def transfer_stock(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    from_location_type: str,
    from_location_id: int,
    to_location_type: str,
    to_location_id: int,
    qty,
    note: Optional[str] = None
):
    """
    Transferencia: resta en origen y suma en destino.
    Registra un SOLO kardex con from_ y to_.
    """
    if from_location_type not in LocationType.ALL or to_location_type not in LocationType.ALL:
        raise ValueError("location_type inválido")

    q = _to_qty(qty)
    if q <= 0:
        raise ValueError("qty debe ser > 0")

    inv_from = get_or_create_inventory(
        db,
        company_id=company_id,
        product_id=product_id,
        location_type=from_location_type,
        location_id=from_location_id,
    )
    current = _to_qty(inv_from.qty)
    if current < q:
        raise ValueError(f"Stock insuficiente en origen. Disponible={current} requerido={q}")

    inv_to = get_or_create_inventory(
        db,
        company_id=company_id,
        product_id=product_id,
        location_type=to_location_type,
        location_id=to_location_id,
    )

    inv_from.qty = current - q
    inv_to.qty = _to_qty(inv_to.qty) + q

    km = KardexMovement(
        company_id=company_id,
        product_id=product_id,
        move_type=KardexMoveType.TRANSFER,
        from_location_type=from_location_type,
        from_location_id=from_location_id,
        to_location_type=to_location_type,
        to_location_id=to_location_id,
        qty=q,
        note=note,
    )
    db.add(km)
    db.flush()
    return inv_from, inv_to, km
