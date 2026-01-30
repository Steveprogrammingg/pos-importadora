from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user

from models import db
from models.branch import Branch
from models.product import Product
from models.membership import Role
from models.inventory import LocationType
from models.kardex import KardexMoveType
from models.stock_transfer import StockTransfer, StockTransferItem
from routes.guards import require_context, require_roles

from services.stock import add_stock, transfer_stock

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


@inventory_bp.get("/in")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def stock_in_get():
    """
    Entrada a Bodega Central (compra/ingreso).
    """
    company_id = _company_id()

    warehouse = (
        db.session.query(Branch)
        .filter(
            Branch.company_id == company_id,
            Branch.is_warehouse == True,
            Branch.is_active == True
        )
        .first()
    )
    if not warehouse:
        flash("No existe Bodega Central activa para esta empresa.", "error")
        return redirect(url_for("main.dashboard"))

    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .order_by(Product.name.asc())
        .all()
    )

    return render_template("inventory_in.html", warehouse=warehouse, products=products)


@inventory_bp.post("/in")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def stock_in_post():
    company_id = _company_id()
    warehouse_id = int(request.form.get("warehouse_id") or 0)
    product_id = int(request.form.get("product_id") or 0)
    qty = request.form.get("qty") or "0"
    note = (request.form.get("note") or "").strip()

    wh = db.session.query(Branch).filter_by(id=warehouse_id, company_id=company_id, is_warehouse=True).first()
    if not wh:
        flash("Bodega inválida.", "error")
        return redirect(url_for("inventory.stock_in_get"))

    product = db.session.query(Product).filter_by(id=product_id, company_id=company_id).first()
    if not product:
        flash("Producto inválido.", "error")
        return redirect(url_for("inventory.stock_in_get"))

    try:
        add_stock(
            db.session,
            company_id=company_id,
            product_id=product.id,
            location_type=LocationType.WAREHOUSE,
            location_id=wh.id,
            qty=qty,
            move_type=KardexMoveType.PURCHASE_IN,
            note=note or "Ingreso a bodega",
        )
        db.session.commit()
        flash("Ingreso registrado en bodega.", "message")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("inventory.stock_in_get"))


@inventory_bp.get("/transfer")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def transfer_get():
    company_id = _company_id()

    branches = (
        db.session.query(Branch)
        .filter(Branch.company_id == company_id, Branch.is_active == True)
        .order_by(Branch.is_warehouse.desc(), Branch.name.asc())
        .all()
    )
    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .order_by(Product.name.asc())
        .all()
    )
    products_json = [
        {"id": p.id, "name": p.name, "sku": p.sku or ""}
        for p in products
    ]
    return render_template(
        "inventory_transfer.html",
        branches=branches,
        products=products,
        products_json=products_json,
    )


@inventory_bp.post("/transfer")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def transfer_post():
    company_id = _company_id()
    from_branch_id = int(request.form.get("from_branch_id") or 0)
    to_branch_id = int(request.form.get("to_branch_id") or 0)
    note = (request.form.get("note") or "").strip()
    action = (request.form.get("action") or "confirm").strip().lower()

    product_ids = request.form.getlist("product_id[]")
    qtys = request.form.getlist("qty[]")

    # Normaliza items
    items: list[tuple[int, str]] = []
    for pid, q in zip(product_ids, qtys):
        try:
            pid_i = int(pid or 0)
        except ValueError:
            pid_i = 0
        q_s = (q or "0").strip()
        if pid_i and q_s and q_s not in ("0", "0.0", "0.00"):
            items.append((pid_i, q_s))

    if not items:
        flash("Agrega al menos un producto con cantidad.", "error")
        return redirect(url_for("inventory.transfer_get"))

    if from_branch_id == to_branch_id:
        flash("Origen y destino no pueden ser iguales.", "error")
        return redirect(url_for("inventory.transfer_get"))

    # Validación de productos
    products_map = {
        p.id: p
        for p in db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .all()
    }
    for pid, _ in items:
        if pid not in products_map:
            flash("Uno o más productos son inválidos.", "error")
            return redirect(url_for("inventory.transfer_get"))

    b_from = db.session.query(Branch).filter_by(id=from_branch_id, company_id=company_id, is_active=True).first()
    b_to = db.session.query(Branch).filter_by(id=to_branch_id, company_id=company_id, is_active=True).first()
    if not b_from or not b_to:
        flash("Sucursal/Bodega inválida.", "error")
        return redirect(url_for("inventory.transfer_get"))

    from_type = LocationType.WAREHOUSE if b_from.is_warehouse else LocationType.BRANCH
    to_type = LocationType.WAREHOUSE if b_to.is_warehouse else LocationType.BRANCH

    try:
        # Crear documento
        t = StockTransfer(
            company_id=company_id,
            from_branch_id=b_from.id,
            to_branch_id=b_to.id,
            note=note or None,
            status="CONFIRMED" if action == "confirm" else "DRAFT",
            confirmed_at=datetime.utcnow() if action == "confirm" else None,
            created_by_user_id=getattr(current_user, "id", None),
        )
        db.session.add(t)
        db.session.flush()

        # Agregar items
        for pid, q in items:
            db.session.add(
                StockTransferItem(
                    transfer_id=t.id,
                    product_id=pid,
                    qty=str(q).replace(",", "."),
                )
            )

        # Si confirma: afectar stock por cada item
        if action == "confirm":
            for pid, q in items:
                transfer_stock(
                    db.session,
                    company_id=company_id,
                    product_id=pid,
                    from_location_type=from_type,
                    from_location_id=b_from.id,
                    to_location_type=to_type,
                    to_location_id=b_to.id,
                    qty=q,
                    note=(note or f"Transferencia #{t.id}"),
                )

        db.session.commit()
        if action == "confirm":
            flash("Transferencia confirmada y aplicada a inventario.", "message")
        else:
            flash("Transferencia guardada como borrador (no afectó inventario).", "message")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("inventory.transfer_history"))


@inventory_bp.get("/transfer/history")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def transfer_history():
    company_id = _company_id()

    transfers = (
        db.session.query(StockTransfer)
        .filter(StockTransfer.company_id == company_id)
        .order_by(StockTransfer.created_at.desc())
        .limit(200)
        .all()
    )

    # preload branches and products for rendering
    branch_map = {b.id: b for b in db.session.query(Branch).filter(Branch.company_id == company_id).all()}
    product_map = {p.id: p for p in db.session.query(Product).filter(Product.company_id == company_id).all()}

    return render_template(
        "inventory_transfer_history.html",
        transfers=transfers,
        branch_map=branch_map,
        product_map=product_map,
    )


@inventory_bp.post("/transfer/<int:transfer_id>/confirm")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def transfer_confirm(transfer_id: int):
    """Confirma un borrador y aplica la transferencia a inventario."""
    company_id = _company_id()

    t = (
        db.session.query(StockTransfer)
        .filter(StockTransfer.id == transfer_id, StockTransfer.company_id == company_id)
        .first()
    )
    if not t:
        flash("Transferencia no encontrada.", "error")
        return redirect(url_for("inventory.transfer_history"))

    if t.status == "CONFIRMED":
        flash("La transferencia ya está confirmada.", "message")
        return redirect(url_for("inventory.transfer_history"))

    b_from = db.session.query(Branch).filter_by(id=t.from_branch_id, company_id=company_id, is_active=True).first()
    b_to = db.session.query(Branch).filter_by(id=t.to_branch_id, company_id=company_id, is_active=True).first()
    if not b_from or not b_to:
        flash("Origen/destino inválido.", "error")
        return redirect(url_for("inventory.transfer_history"))

    from_type = LocationType.WAREHOUSE if b_from.is_warehouse else LocationType.BRANCH
    to_type = LocationType.WAREHOUSE if b_to.is_warehouse else LocationType.BRANCH

    try:
        for it in t.items:
            transfer_stock(
                db.session,
                company_id=company_id,
                product_id=it.product_id,
                from_location_type=from_type,
                from_location_id=b_from.id,
                to_location_type=to_type,
                to_location_id=b_to.id,
                qty=str(it.qty),
                note=(t.note or f"Transferencia #{t.id}"),
            )
        t.status = "CONFIRMED"
        t.confirmed_at = datetime.utcnow()
        db.session.commit()
        flash("Transferencia confirmada y aplicada a inventario.", "message")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al confirmar: {e}", "error")

    return redirect(url_for("inventory.transfer_history"))
