from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from models import db
from models.branch import Branch
from models.company import Company
from models.expense import Expense
from models.sale import Sale
from routes import main_bp
from routes.guards import require_context


@main_bp.get("/")
@login_required
def home():
    if not session.get("company_id") or not session.get("branch_id"):
        return redirect(url_for("context.select_context"))
    return redirect(url_for("main.dashboard"))


@main_bp.get("/dashboard")
@login_required
@require_context()
def dashboard():
    company_id = int(session["company_id"])
    branch_id = int(session["branch_id"])

    company = db.session.get(Company, company_id)
    branch = db.session.get(Branch, branch_id)
    if not company or not branch:
        flash("Contexto inválido. Vuelve a seleccionar.", "error")
        return redirect(url_for("context.select_context"))

    now = datetime.now()
    start_today = datetime(now.year, now.month, now.day)
    end_today = start_today + timedelta(days=1)
    start_last7 = start_today - timedelta(days=6)

    # Totales por agregación (más rápido que iterar)
    today_total = (
        db.session.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= start_today,
            Sale.created_at < end_today,
        )
        .scalar()
    )
    today_count = (
        db.session.query(func.count(Sale.id))
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= start_today,
            Sale.created_at < end_today,
        )
        .scalar()
    )

    last7_total = (
        db.session.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= start_last7,
            Sale.created_at < end_today,
        )
        .scalar()
    )
    last7_count = (
        db.session.query(func.count(Sale.id))
        .filter(
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= start_last7,
            Sale.created_at < end_today,
        )
        .scalar()
    )

    # Gastos hoy
    today_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.company_id == company_id,
            Expense.branch_id == branch_id,
            Expense.expense_date == date.today(),
        )
        .scalar()
    )

    stats = {
        "today_total": float(Decimal(str(today_total))),
        "today_count": int(today_count or 0),
        "last7_total": float(Decimal(str(last7_total))),
        "last7_count": int(last7_count or 0),
        "today_expenses": float(Decimal(str(today_expenses))),
        "today_net": float(Decimal(str(today_total)) - Decimal(str(today_expenses))),
    }

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
        stats=stats,
        recent_sales=recent_sales,
    )
