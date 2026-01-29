from decimal import Decimal, InvalidOperation
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required
from sqlalchemy import func

from models import db
from models.branch import Branch
from models.product import Product
from models.inventory import Inventory, LocationType
from models.membership import Role
from routes.guards import require_context, require_roles
from models.kardex import KardexMovement, KardexMoveType

inventory_admin_bp = Blueprint("inventory_admin", __name__, url_prefix="/inventory-admin")


# -------------------------
# Helpers
# -------------------------
def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


def _clean_str(v: str | None) -> str:
    return (v or "").strip()


def _to_int(v: str | None, default: int = 0) -> int:
    try:
        return int(_clean_str(v))
    except ValueError:
        return default


def _to_decimal_qty(v: str | None) -> Decimal:
    """
    Cantidades con 3 decimales (ej: 1.000)
    Acepta coma o punto.
    """
    raw = _clean_str(v).replace(",", ".")
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0.000")
    return d.quantize(Decimal("0.001"))


def _role() -> str:
    return (_clean_str(session.get("role"))).upper()


def _allowed_branch_id(requested_branch_id: int) -> int:
    """
    Si es SELLER, fuerza su sucursal.
    Si es ADMIN/OWNER, permite elegir.
    """
    current = _branch_id()
    if _role() == Role.SELLER:
        return current
    return requested_branch_id or current


# -------------------------
# Lista de stock por sucursal
# -------------------------
@inventory_admin_bp.get("/stock")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def stock_list():
    company_id = _company_id()

    branch_id_raw = _to_int(request.args.get("branch_id"), 0)
    branch_id = _allowed_branch_id(branch_id_raw)

    q = _clean_str(request.args.get("q"))
    only_low = _clean_str(request.args.get("low")) == "1"

    # sucursales (solo no bodega para vista retail)
    branches = (
        db.session.query(Branch)
        .filter(
            Branch.company_id == company_id,
            Branch.is_active == True,
            Branch.is_warehouse == False,
        )
        .order_by(Branch.name.asc())
        .all()
    )

    # Query: productos + inventario en esa sucursal
    # LEFT JOIN para que aparezca producto aunque no exista fila en inventory todavía.
    inv_alias = db.aliased(Inventory)

    base = (
        db.session.query(
            Product.id.label("product_id"),
            Product.name.label("name"),
            Product.sku.label("sku"),
            Product.barcode.label("barcode"),
            func.coalesce(inv_alias.qty, 0).label("qty"),
        )
        .outerjoin(
            inv_alias,
            (inv_alias.company_id == Product.company_id)
            & (inv_alias.product_id == Product.id)
            & (inv_alias.location_type == LocationType.BRANCH)
            & (inv_alias.location_id == branch_id)
        )
        .filter(Product.company_id == company_id, Product.is_active == True)
    )

    if q:
        like = f"%{q}%"
        base = base.filter(
            (Product.name.ilike(like))
            | (Product.sku.ilike(like))
            | (Product.barcode.ilike(like))
        )

    if only_low:
        # bajo stock: <= 0 o <= 1 (ajusta si quieres)
        base = base.filter(func.coalesce(inv_alias.qty, 0) <= 0)

    rows = base.order_by(Product.name.asc()).limit(500).all()

    # branch seleccionado
    selected_branch = db.session.get(Branch, branch_id)

    return render_template(
        "inventory_stock.html",
        branches=branches,
        selected_branch_id=branch_id,
        selected_branch=selected_branch,
        rows=rows,
        q=q,
        only_low=only_low,
        role=_role(),
    )


# -------------------------
# Ajuste manual de stock (ADMIN/OWNER)
# -------------------------
@inventory_admin_bp.post("/stock/adjust")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def stock_adjust_post():
    """
    Ajusta stock a mano:
    - puede sumar (+) o restar (-)
    - registra Kardex ADJUST
    - actualiza Inventory
    """
    company_id = _company_id()

    branch_id = _allowed_branch_id(_to_int(request.form.get("branch_id"), _branch_id()))
    product_id = _to_int(request.form.get("product_id"), 0)

    qty_delta = _to_decimal_qty(request.form.get("qty_delta"))
    note = _clean_str(request.form.get("note")) or "Ajuste manual"

    if product_id <= 0:
        flash("Producto inválido.", "error")
        return redirect(url_for("inventory_admin.stock_list", branch_id=branch_id))

    if qty_delta == 0:
        flash("Cantidad inválida (usa + o -).", "error")
        return redirect(url_for("inventory_admin.stock_list", branch_id=branch_id))

    product = (
        db.session.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id, Product.is_active == True)
        .first()
    )
    if not product:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("inventory_admin.stock_list", branch_id=branch_id))

    inv = (
        db.session.query(Inventory)
        .filter(
            Inventory.company_id == company_id,
            Inventory.product_id == product_id,
            Inventory.location_type == LocationType.BRANCH,
            Inventory.location_id == branch_id,
        )
        .first()
    )
    if not inv:
        inv = Inventory(
            company_id=company_id,
            product_id=product_id,
            location_type=LocationType.BRANCH,
            location_id=branch_id,
            qty=Decimal("0.000"),
        )
        db.session.add(inv)
        db.session.flush()

    new_qty = Decimal(str(inv.qty)) + qty_delta
    if new_qty < 0:
        flash("No puedes dejar stock negativo.", "error")
        return redirect(url_for("inventory_admin.stock_list", branch_id=branch_id))

    inv.qty = new_qty

    # Kardex: ADJUST
    km = KardexMovement(
        company_id=company_id,
        product_id=product_id,
        move_type=KardexMoveType.ADJUST,
        from_location_type=None if qty_delta > 0 else LocationType.BRANCH,
        from_location_id=None if qty_delta > 0 else branch_id,
        to_location_type=LocationType.BRANCH if qty_delta > 0 else None,
        to_location_id=branch_id if qty_delta > 0 else None,
        qty=abs(qty_delta),
        unit_cost=None,
        note=note,
        created_at=datetime.utcnow(),
    )
    db.session.add(km)

    db.session.commit()
    flash("Stock ajustado correctamente.", "message")
    return redirect(url_for("inventory_admin.stock_list", branch_id=branch_id))
