from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, session, flash
from flask_login import login_required
from sqlalchemy import func

from models import db
from models.sale import Sale, SaleItem
from models.product import Product
from models.branch import Branch
from models.membership import Role
from routes.guards import require_context, require_roles

reports_top_bp = Blueprint("reports_top", __name__, url_prefix="/reports-top")


def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


def _parse_date_start(s: str | None, default: datetime) -> datetime:
    """Acepta YYYY-MM-DD. Devuelve datetime a las 00:00:00."""
    if not s:
        return default.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
        return d.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return default.replace(hour=0, minute=0, second=0, microsecond=0)


def _clamp_int(val: str | None, default: int, min_v: int, max_v: int) -> int:
    try:
        n = int((val or "").strip())
    except ValueError:
        n = default
    if n < min_v:
        return min_v
    if n > max_v:
        return max_v
    return n


@reports_top_bp.get("/top-products")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def top_products():
    """
    Top productos por:
    - cantidad vendida (SUM(qty))
    - total vendido (SUM(subtotal))

    Filtros:
    - from, to (YYYY-MM-DD)
    - branch_id (solo admin/owner pueden cambiar, seller queda en su sucursal)
    - limit (default 20, 5..200)
    """
    company_id = _company_id()
    current_branch_id = _branch_id()

    # Defaults: últimos 7 días (incluye hoy)
    now = datetime.now()
    default_from = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    default_to = now.replace(hour=0, minute=0, second=0, microsecond=0)

    date_from = _parse_date_start(request.args.get("from"), default_from)
    date_to = _parse_date_start(request.args.get("to"), default_to)
    date_to_end = date_to + timedelta(days=1)  # exclusivo

    limit_n = _clamp_int(request.args.get("limit"), default=20, min_v=5, max_v=200)

    # Branch filter
    branch_id = current_branch_id
    branch_filter = request.args.get("branch_id")
    if branch_filter:
        try:
            branch_id = int(branch_filter)
        except ValueError:
            branch_id = current_branch_id

    # Seguridad práctica: si es SELLER, forzar sucursal actual
    role = (session.get("role") or "").upper()
    if role == Role.SELLER:
        branch_id = current_branch_id

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

    # Query base agregada
    base_q = (
        db.session.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("sku"),
            Product.barcode.label("barcode"),
            func.coalesce(func.sum(SaleItem.qty), 0).label("qty_sum"),
            func.coalesce(func.sum(SaleItem.subtotal), 0).label("amount_sum"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= date_from,
            Sale.created_at < date_to_end,
        )
        .group_by(Product.id, Product.name, Product.sku, Product.barcode)
    )

    top_by_qty = base_q.order_by(func.sum(SaleItem.qty).desc()).limit(limit_n).all()
    top_by_amount = base_q.order_by(func.sum(SaleItem.subtotal).desc()).limit(limit_n).all()

    # Totales exactos del rango (no dependen del top)
    totals = (
        db.session.query(
            func.coalesce(func.sum(SaleItem.qty), 0),
            func.coalesce(func.sum(SaleItem.subtotal), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= date_from,
            Sale.created_at < date_to_end,
        )
        .first()
    )

    total_qty = Decimal(str(totals[0] or 0)).quantize(Decimal("0.001"))
    total_amount = Decimal(str(totals[1] or 0)).quantize(Decimal("0.01"))

    return render_template(
        "reports_top_products.html",
        branches=branches,
        selected_branch_id=branch_id,
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        limit_n=limit_n,
        top_by_qty=top_by_qty,
        top_by_amount=top_by_amount,
        total_qty=float(total_qty),
        total_amount=float(total_amount),
    )
