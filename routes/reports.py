from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, session, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from models import db
from models.sale import Sale, SaleItem
from models.branch import Branch
from models.membership import CompanyUser, Role
from routes.guards import require_context, require_roles

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


def _parse_date(s: str | None, default: datetime) -> datetime:
    """Acepta YYYY-MM-DD. Devuelve datetime a las 00:00:00."""
    if not s:
        return default
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        return default


def _get_role_in_context(company_id: int, branch_id: int) -> str:
    """
    Rol efectivo del usuario en el contexto actual.
    - Si tiene ADMIN/OWNER a nivel empresa (branch_id=None), eso manda.
    - Si no, busca rol por sucursal.
    """
    # 1) rol empresa (branch_id is NULL)
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

    # 2) rol por sucursal
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


@reports_bp.get("/sales")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def sales_list():
    """
    Reporte: Ventas por rango de fechas.
    - SELLER: solo su sucursal.
    - ADMIN/OWNER: puede filtrar por sucursal o ver "todas".
    """
    company_id = _company_id()
    current_branch_id = _branch_id()

    role = _get_role_in_context(company_id, current_branch_id)

    # Defaults: últimos 7 días
    today = datetime.now()
    default_from = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    default_to = today.replace(hour=0, minute=0, second=0, microsecond=0)

    date_from = _parse_date(request.args.get("from"), default_from)
    date_to = _parse_date(request.args.get("to"), default_to)

    # date_to inclusive -> fin de día (sumamos 1 día y usamos <)
    date_to_end = date_to + timedelta(days=1)

    # Branch filter:
    # - SELLER: fijo a su sucursal
    # - ADMIN/OWNER: puede elegir branch_id o ALL
    branch_param = (request.args.get("branch_id") or "").strip()
    selected_branch_id: int | None

    if role == Role.SELLER:
        selected_branch_id = current_branch_id
    else:
        if branch_param.lower() in ("", "all", "0"):
            selected_branch_id = None  # todas
        else:
            try:
                selected_branch_id = int(branch_param)
            except ValueError:
                selected_branch_id = None

            # Validar que la sucursal pertenezca a la empresa y esté activa (y no sea bodega)
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

    # Lista de sucursales para el select (solo no-bodega)
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

    # Query base
    base = (
        db.session.query(Sale)
        .filter(
            Sale.company_id == company_id,
            Sale.created_at >= date_from,
            Sale.created_at < date_to_end,
        )
    )

    if selected_branch_id is not None:
        base = base.filter(Sale.branch_id == selected_branch_id)

    # Listado (limit 200)
    sales = base.order_by(Sale.created_at.desc()).limit(200).all()

    # Totales reales del rango (sin depender del limit)
    # Totales del rango
    agg_sales = db.session.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total), 0),
    ).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        agg_sales = agg_sales.filter(Sale.branch_id == selected_branch_id)

    total_count, total_sum = agg_sales.first()
    total_amount = Decimal(str(total_sum or 0)).quantize(Decimal("0.01"))

    # Costo y ganancia (usa unit_cost fotografiado en SaleItem)
    agg_profit = db.session.query(
        func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.qty), 0),
        func.coalesce(func.sum((SaleItem.unit_price - SaleItem.unit_cost) * SaleItem.qty), 0),
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        agg_profit = agg_profit.filter(Sale.branch_id == selected_branch_id)

    total_cost_sum, total_profit_sum = agg_profit.first()
    total_cost = Decimal(str(total_cost_sum or 0)).quantize(Decimal("0.01"))
    total_profit = Decimal(str(total_profit_sum or 0)).quantize(Decimal("0.01"))

    return render_template(
        "reports_sales.html",
        sales=sales,
        branches=branches,
        selected_branch_id=(selected_branch_id or 0),
        role=role,
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        total_amount=float(total_amount),
        total_cost=float(total_cost),
        total_profit=float(total_profit),
        total_count=int(total_count or 0),
    )
