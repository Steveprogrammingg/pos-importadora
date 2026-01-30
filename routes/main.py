from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import flash, redirect, render_template, session, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import func

from models import db
from models.branch import Branch
from models.company import Company
from models.expense import Expense
from models.inventory import Inventory, LocationType
from models.product import Product
from models.sale import Sale, SaleItem
from routes import main_bp
from routes.guards import require_context, require_roles
from models.membership import Role


def _money(v) -> float:
    """Safe decimal/numeric -> float."""
    try:
        return float(Decimal(str(v)))
    except Exception:
        return float(v or 0)


def _img_url(image_path, image_updated_at):
    if not image_path:
        return None
    base_url = url_for("static", filename=image_path)
    if image_updated_at:
        return f"{base_url}?v={int(image_updated_at.timestamp())}"
    return base_url


def _dashboard_payload(company_id: int, branch_id: int):
    """Compute dashboard metrics from DB (fast aggregations)."""
    now = datetime.now()
    start_today = datetime(now.year, now.month, now.day)
    end_today = start_today + timedelta(days=1)

    start_month = datetime(now.year, now.month, 1)
    if now.month == 12:
        end_month = datetime(now.year + 1, 1, 1)
    else:
        end_month = datetime(now.year, now.month + 1, 1)

    base_sales_filters = (Sale.company_id == company_id, Sale.branch_id == branch_id)

    def _sales_sum(start_dt, end_dt):
        total = (
            db.session.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(*base_sales_filters, Sale.created_at >= start_dt, Sale.created_at < end_dt)
            .scalar()
        )
        count = (
            db.session.query(func.count(Sale.id))
            .filter(*base_sales_filters, Sale.created_at >= start_dt, Sale.created_at < end_dt)
            .scalar()
        )
        cash = (
            db.session.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(
                *base_sales_filters,
                Sale.created_at >= start_dt,
                Sale.created_at < end_dt,
                Sale.payment_method == "cash",
            )
            .scalar()
        )
        transfer = (
            db.session.query(func.coalesce(func.sum(Sale.total), 0))
            .filter(
                *base_sales_filters,
                Sale.created_at >= start_dt,
                Sale.created_at < end_dt,
                Sale.payment_method == "transfer",
            )
            .scalar()
        )
        return _money(total), int(count or 0), _money(cash), _money(transfer)

    today_total, today_count, today_cash, today_transfer = _sales_sum(start_today, end_today)
    month_total, month_count, month_cash, month_transfer = _sales_sum(start_month, end_month)

    # profit = sum( (unit_price - unit_cost) * qty - discount )
    profit_expr = ((SaleItem.unit_price - SaleItem.unit_cost) * SaleItem.qty) - func.coalesce(SaleItem.discount, 0)

    today_gross_profit = (
        db.session.query(func.coalesce(func.sum(profit_expr), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*base_sales_filters, Sale.created_at >= start_today, Sale.created_at < end_today)
        .scalar()
    )
    month_gross_profit = (
        db.session.query(func.coalesce(func.sum(profit_expr), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*base_sales_filters, Sale.created_at >= start_month, Sale.created_at < end_month)
        .scalar()
    )

    today_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.company_id == company_id, Expense.branch_id == branch_id, Expense.expense_date == date.today())
        .scalar()
    )
    month_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.company_id == company_id,
            Expense.branch_id == branch_id,
            Expense.expense_date >= start_month.date(),
            Expense.expense_date < end_month.date(),
        )
        .scalar()
    )

    from flask import current_app
    threshold = int(getattr(current_app.config, "STOCK_LOW_THRESHOLD", 5))

    top_products_rows = (
        db.session.query(
            Product.id,
            Product.name,
            Product.image_path,
            Product.image_updated_at,
            func.coalesce(func.sum(SaleItem.qty), 0).label("qty_sold"),
            func.coalesce(func.sum(SaleItem.subtotal), 0).label("amount"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Product.company_id == company_id, *base_sales_filters, Sale.created_at >= start_month, Sale.created_at < end_month)
        .group_by(Product.id)
        .order_by(func.sum(SaleItem.qty).desc())
        .limit(5)
        .all()
    )

    low_stock_rows = (
        db.session.query(Product.id, Product.name, Inventory.qty, Product.image_path, Product.image_updated_at)
        .join(Inventory, Inventory.product_id == Product.id)
        .filter(
            Inventory.company_id == company_id,
            Inventory.location_type == LocationType.BRANCH,
            Inventory.location_id == branch_id,
            Inventory.qty <= threshold,
        )
        .order_by(Inventory.qty.asc())
        .limit(8)
        .all()
    )

    payload = {
        "now_iso": now.isoformat(timespec="seconds"),
        "today": {
            "total": today_total,
            "count": today_count,
            "cash": today_cash,
            "transfer": today_transfer,
            "gross_profit": _money(today_gross_profit),
            "expenses": _money(today_expenses),
            "net": _money(Decimal(str(today_gross_profit)) - Decimal(str(today_expenses))),
        },
        "month": {
            "total": month_total,
            "count": month_count,
            "cash": month_cash,
            "transfer": month_transfer,
            "gross_profit": _money(month_gross_profit),
            "expenses": _money(month_expenses),
            "net": _money(Decimal(str(month_gross_profit)) - Decimal(str(month_expenses))),
        },
        "top_products": [
            {
                "id": int(r.id),
                "name": r.name,
                "qty_sold": float(r.qty_sold),
                "amount": _money(r.amount),
                "image_url": _img_url(r.image_path, r.image_updated_at),
            }
            for r in top_products_rows
        ],
        "low_stock": [
            {
                "id": int(r.id),
                "name": r.name,
                "qty": float(r.qty),
                "image_url": _img_url(r.image_path, r.image_updated_at),
            }
            for r in low_stock_rows
        ],
    }
    return payload


@main_bp.get("/")
@login_required
def home():
    if not session.get("company_id") or not session.get("branch_id"):
        return redirect(url_for("context.select_context"))
    return redirect(url_for("main.dashboard"))


@main_bp.get("/dashboard")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def dashboard():
    company_id = int(session["company_id"])
    branch_id = int(session["branch_id"])

    company = db.session.get(Company, company_id)
    branch = db.session.get(Branch, branch_id)
    if not company or not branch:
        flash("Contexto inválido. Vuelve a seleccionar.", "error")
        return redirect(url_for("context.select_context"))

    payload = _dashboard_payload(company_id, branch_id)

    recent_sales = (
        db.session.query(Sale)
        .filter(Sale.company_id == company_id, Sale.branch_id == branch_id)
        .order_by(Sale.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard.html",
        company=company,
        branch=branch,
        user=current_user,
        stats=payload,
        recent_sales=recent_sales,
    )


@main_bp.get("/dashboard/stats")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def dashboard_stats():
    company_id = int(session["company_id"])
    branch_id = int(session["branch_id"])
    payload = _dashboard_payload(company_id, branch_id)
    return jsonify(payload)
