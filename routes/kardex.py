from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import login_required

from models import db
from models.kardex import KardexMovement, KardexMoveType
from models.product import Product
from models.branch import Branch
from models.membership import Role
from routes.guards import require_context, require_roles

kardex_bp = Blueprint("kardex", __name__, url_prefix="/kardex")


def _company_id() -> int:
    return int(session["company_id"])


def _parse_date(s: str | None, default: datetime) -> datetime:
    if not s:
        return default
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        return default


@kardex_bp.get("/")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def list_kardex():
    company_id = _company_id()

    # Defaults: últimos 7 días
    today = datetime.now()
    default_from = today - timedelta(days=6)
    default_to = today

    date_from = _parse_date(request.args.get("from"), default_from)
    date_to = _parse_date(request.args.get("to"), default_to)
    date_to_end = date_to + timedelta(days=1)

    product_q = (request.args.get("product_q") or "").strip()
    product_id_raw = (request.args.get("product_id") or "").strip()
    move_type = (request.args.get("move_type") or "").strip().upper()
    location_id_raw = (request.args.get("location_id") or "").strip()

    # Productos (para select / helper)
    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .order_by(Product.name.asc())
        .limit(300)
        .all()
    )

    # Ubicaciones (branches + bodega(s))
    locations = (
        db.session.query(Branch)
        .filter(Branch.company_id == company_id, Branch.is_active == True)
        .order_by(Branch.is_warehouse.desc(), Branch.name.asc())
        .all()
    )

    # Resolver product_id:
    product_id = None
    if product_id_raw:
        try:
            product_id = int(product_id_raw)
        except ValueError:
            product_id = None

    if not product_id and product_q:
        # Buscar por barcode o sku exacto
        p = (
            db.session.query(Product)
            .filter(
                Product.company_id == company_id,
                Product.is_active == True,
                (Product.barcode == product_q) | (Product.sku == product_q)
            )
            .first()
        )
        # Si no, por nombre
        if not p:
            p = (
                db.session.query(Product)
                .filter(
                    Product.company_id == company_id,
                    Product.is_active == True,
                    Product.name.ilike(f"%{product_q}%")
                )
                .order_by(Product.name.asc())
                .first()
            )
        if p:
            product_id = p.id
        elif product_q:
            flash("No se encontró el producto con ese criterio.", "error")

    # Location
    location_id = None
    if location_id_raw:
        try:
            location_id = int(location_id_raw)
        except ValueError:
            location_id = None

    q = (
        db.session.query(KardexMovement)
        .filter(
            KardexMovement.company_id == company_id,
            KardexMovement.created_at >= date_from,
            KardexMovement.created_at < date_to_end,
        )
        .order_by(KardexMovement.created_at.desc(), KardexMovement.id.desc())
    )

    if product_id:
        q = q.filter(KardexMovement.product_id == product_id)

    if move_type and move_type in KardexMoveType.ALL:
        q = q.filter(KardexMovement.move_type == move_type)

    # Filtrar por ubicación: si aparece como origen o destino
    if location_id:
        q = q.filter(
            (KardexMovement.from_location_id == location_id) |
            (KardexMovement.to_location_id == location_id)
        )

    movements = q.limit(300).all()

    # Mapas para mostrar nombres sin joins pesados
    product_map = {p.id: p for p in products}
    location_map = {b.id: b for b in locations}

    return render_template(
        "kardex_list.html",
        movements=movements,
        products=products,
        locations=locations,
        product_map=product_map,
        location_map=location_map,
        move_types=sorted(list(KardexMoveType.ALL)),
        selected_move_type=move_type,
        selected_product_id=product_id,
        selected_location_id=location_id,
        product_q=product_q,
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
    )
