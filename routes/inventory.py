from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required

from models import db
from models.branch import Branch
from models.product import Product
from models.membership import Role
from models.inventory import LocationType
from models.kardex import KardexMoveType
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
    return render_template("inventory_transfer.html", branches=branches, products=products)


@inventory_bp.post("/transfer")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def transfer_post():
    company_id = _company_id()

    product_id = int(request.form.get("product_id") or 0)
    from_branch_id = int(request.form.get("from_branch_id") or 0)
    to_branch_id = int(request.form.get("to_branch_id") or 0)
    qty = request.form.get("qty") or "0"
    note = (request.form.get("note") or "").strip()

    if from_branch_id == to_branch_id:
        flash("Origen y destino no pueden ser iguales.", "error")
        return redirect(url_for("inventory.transfer_get"))

    product = db.session.query(Product).filter_by(id=product_id, company_id=company_id).first()
    if not product:
        flash("Producto inválido.", "error")
        return redirect(url_for("inventory.transfer_get"))

    b_from = db.session.query(Branch).filter_by(id=from_branch_id, company_id=company_id, is_active=True).first()
    b_to = db.session.query(Branch).filter_by(id=to_branch_id, company_id=company_id, is_active=True).first()
    if not b_from or not b_to:
        flash("Sucursal/Bodega inválida.", "error")
        return redirect(url_for("inventory.transfer_get"))

    from_type = LocationType.WAREHOUSE if b_from.is_warehouse else LocationType.BRANCH
    to_type = LocationType.WAREHOUSE if b_to.is_warehouse else LocationType.BRANCH

    try:
        transfer_stock(
            db.session,
            company_id=company_id,
            product_id=product.id,
            from_location_type=from_type,
            from_location_id=b_from.id,
            to_location_type=to_type,
            to_location_id=b_to.id,
            qty=qty,
            note=note or "Transferencia",
        )
        db.session.commit()
        flash("Transferencia registrada.", "message")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("inventory.transfer_get"))
