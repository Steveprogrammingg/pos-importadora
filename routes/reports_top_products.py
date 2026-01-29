from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, session, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db
from models.sale import Sale, SaleItem
from models.product import Product
from models.branch import Branch
from models.membership import CompanyUser, Role
from routes.guards import require_context, require_roles

reports_top_bp = Blueprint("reports_top", __name__, url_prefix="/reports")


def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


def _parse_date(s: str | None, default: datetime) -> datetime:
    if not s:
        return default
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        return default


def _get_role_in_context(company_id: int, branch_id: int) -> str:
    m_company = (
        db.session.query(CompanyUser)
        .filter(
            CompanyUser.company_id == company_id,
            CompanyUser.user_id == current_user.id,
            CompanyUser.branch_id.is_(None),
            CompanyUser.is_active == True,
        )
        .first()
    )
    if m_company:
        return m_company.role

    m_branch = (
        db.session.query(CompanyUser)
        .filter(
            CompanyUser.company_id == company_id,
            CompanyUser.user_id == current_user.id,
            CompanyUser.branch_id == branch_id,
            CompanyUser.is_active == True,
        )
        .first()
    )
    return m_branch.role if m_branch else Role.SELLER


@reports_top_bp.get("/top-products")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def top_products():
    """
    Reporte: productos más vendidos (cantidad y total).
    - SELLER: solo su sucursal.
    - ADMIN/OWNER: puede filtrar sucursal o ver todas.
    """
    company_id = _company_id()
    current_branch_id = _branch_id()
    role = _get_role_in_context(company_id, current_branch_id)

    today = datetime.now()
    default_from = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    default_to = today.replace(hour=0, minute=0, second=0, microsecond=0)

    date_from = _parse_date(request.args.get("from"), default_from)
    date_to = _parse_date(request.args.get("to"), default_to)
    date_to_end = date_to + timedelta(days=1)

    branch_param = (request.args.get("branch_id") or "").strip()
    selected_branch_id: int | None

    if role == Role.SELLER:
        selected_branch_id = current_branch_id
    else:
        if branch_param.lower() in ("", "all", "0"):
            selected_branch_id = None
        else:
            try:
                selected_branch_id = int(branch_param)
            except ValueError:
                selected_branch_id = None

            if selected_branch_id is not None:
                ok = (
                    db.session.query(Branch)
                    .filter(
                        Branch.id == selected_branch_id,
                        Branch.company_id == company_id,
                        Branch.is_active == True,
                        Branch.is_warehouse == False,
                    )
                    .first()
                )
                if not ok:
                    flash("Sucursal inválida para filtrar. Mostrando todas.", "error")
                    selected_branch_id = None

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

    # Query: agrupar por producto y sumar qty / subtotal
    q = (
        db.session.query(
            SaleItem.product_id.label("product_id"),
            func.coalesce(func.sum(SaleItem.qty), 0).label("qty_sum"),
            func.coalesce(func.sum(SaleItem.subtotal), 0).label("amount_sum"),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == company_id,
            Sale.created_at >= date_from,
            Sale.created_at < date_to_end,
        )
    )

    if selected_branch_id is not None:
        q = q.filter(Sale.branch_id == selected_branch_id)

    rows = (
        q.group_by(SaleItem.product_id)
        .order_by(func.sum(SaleItem.subtotal).desc())
        .limit(50)
        .all()
    )

    # Traer nombres de productos en 1 query
    product_ids = [r.product_id for r in rows]
    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.id.in_(product_ids))
        .all()
    )
    prod_map = {p.id: p for p in products}

    result = []
    total_qty = Decimal("0")
    total_amount = Decimal("0.00")

    for r in rows:
        p = prod_map.get(r.product_id)
        name = p.name if p else f"Producto #{r.product_id}"
        sku = p.sku if p else None
        barcode = p.barcode if p else None

        qty = Decimal(str(r.qty_sum or 0))
        amount = Decimal(str(r.amount_sum or 0)).quantize(Decimal("0.01"))

        total_qty += qty
        total_amount += amount

        result.append({
            "product_id": r.product_id,
            "name": name,
            "sku": sku,
            "barcode": barcode,
            "qty": float(qty),
            "amount": float(amount),
        })

    return render_template(
        "reports_top_products.html",
        role=role,
        branches=branches,
        selected_branch_id=(selected_branch_id or 0),
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        items=result,
        total_qty=float(total_qty),
        total_amount=float(total_amount),
    )
