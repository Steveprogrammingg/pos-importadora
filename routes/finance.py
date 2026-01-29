from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required

from models import db
from models.cash_movement import CashMovement, CashMoveType
from models.expense import Expense, ExpenseCategory, PaymentMethod
from models.membership import Role
from routes.guards import require_context, require_roles


finance_bp = Blueprint("finance", __name__, url_prefix="/finance")


def _ctx_ids() -> tuple[int, int]:
    return int(session["company_id"]), int(session["branch_id"])


def _as_date(v: str | None, fallback: date) -> date:
    try:
        if v:
            return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        pass
    return fallback


def _money(v: str | None) -> Decimal:
    try:
        return Decimal((v or "0").replace(",", "."))
    except Exception:
        return Decimal("0")


@finance_bp.get("/")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def dashboard():
    company_id, branch_id = _ctx_ids()
    today = date.today()
    start7 = today - timedelta(days=6)

    # Ventas 7 días (suma de sales.total)
    from models.sale import Sale

    sales_last7 = (
        db.session.query(Sale)
        .filter(Sale.company_id == company_id, Sale.branch_id == branch_id, Sale.created_at >= start7)
        .all()
    )
    sales_total = sum(Decimal(str(s.total)) for s in sales_last7)

    expenses_last7 = (
        db.session.query(Expense)
        .filter(Expense.company_id == company_id, Expense.branch_id == branch_id, Expense.expense_date >= start7)
        .all()
    )
    expenses_total = sum(Decimal(str(e.amount)) for e in expenses_last7)

    cash_last7 = (
        db.session.query(CashMovement)
        .filter(CashMovement.company_id == company_id, CashMovement.branch_id == branch_id, CashMovement.move_date >= start7)
        .all()
    )
    cash_in = sum(Decimal(str(m.amount)) for m in cash_last7 if m.move_type == CashMoveType.IN_)
    cash_out = sum(Decimal(str(m.amount)) for m in cash_last7 if m.move_type == CashMoveType.OUT)

    return render_template(
        "finance_dashboard.html",
        sales_total=float(sales_total),
        expenses_total=float(expenses_total),
        cash_in=float(cash_in),
        cash_out=float(cash_out),
        start7=start7,
        today=today,
    )


@finance_bp.get("/expenses")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def expenses_list():
    company_id, branch_id = _ctx_ids()
    today = date.today()
    start = _as_date(request.args.get("start"), today - timedelta(days=30))
    end = _as_date(request.args.get("end"), today)

    q = (
        db.session.query(Expense)
        .filter(
            Expense.company_id == company_id,
            Expense.branch_id == branch_id,
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        )
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
    )

    expenses = q.all()
    total = sum(Decimal(str(e.amount)) for e in expenses)
    return render_template(
        "finance_expenses.html",
        expenses=expenses,
        total=float(total),
        start=start,
        end=end,
        categories=sorted(ExpenseCategory.ALL),
        pay_methods=sorted(PaymentMethod.ALL),
    )


@finance_bp.get("/expenses/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def expenses_new_get():
    return render_template(
        "finance_expense_new.html",
        categories=sorted(ExpenseCategory.ALL),
        pay_methods=sorted(PaymentMethod.ALL),
        today=date.today().strftime("%Y-%m-%d"),
    )


@finance_bp.post("/expenses/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def expenses_new_post():
    company_id, branch_id = _ctx_ids()

    d = _as_date(request.form.get("expense_date"), date.today())
    category = (request.form.get("category") or "OTHER").strip().upper()
    if category not in ExpenseCategory.ALL:
        category = ExpenseCategory.OTHER

    amount = _money(request.form.get("amount"))
    if amount <= 0:
        flash("El monto debe ser mayor a 0.", "error")
        return redirect(url_for("finance.expenses_new_get"))

    payment_method = (request.form.get("payment_method") or PaymentMethod.CASH).strip().upper()
    if payment_method not in PaymentMethod.ALL:
        payment_method = PaymentMethod.CASH

    vendor = (request.form.get("vendor") or "").strip() or None
    note = (request.form.get("note") or "").strip() or None

    e = Expense(
        company_id=company_id,
        branch_id=branch_id,
        expense_date=d,
        category=category,
        amount=amount,
        payment_method=payment_method,
        vendor=vendor,
        note=note,
        created_at=datetime.utcnow(),
    )
    db.session.add(e)
    db.session.commit()

    flash("Gasto registrado.", "message")
    return redirect(url_for("finance.expenses_list"))


@finance_bp.get("/cash")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def cash_dashboard():
    company_id, branch_id = _ctx_ids()
    today = date.today()
    d = _as_date(request.args.get("d"), today)

    moves = (
        db.session.query(CashMovement)
        .filter(CashMovement.company_id == company_id, CashMovement.branch_id == branch_id, CashMovement.move_date == d)
        .order_by(CashMovement.id.desc())
        .all()
    )
    total_in = sum(Decimal(str(m.amount)) for m in moves if m.move_type == CashMoveType.IN_)
    total_out = sum(Decimal(str(m.amount)) for m in moves if m.move_type == CashMoveType.OUT)
    net = total_in - total_out

    return render_template(
        "finance_cash_dashboard.html",
        d=d,
        moves=moves,
        total_in=float(total_in),
        total_out=float(total_out),
        net=float(net),
        move_types=[CashMoveType.IN_, CashMoveType.OUT],
    )


@finance_bp.post("/cash/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER, Role.SELLER)
def cash_new_post():
    company_id, branch_id = _ctx_ids()
    d = _as_date(request.form.get("move_date"), date.today())
    move_type = (request.form.get("move_type") or CashMoveType.IN_).strip().upper()
    if move_type not in CashMoveType.ALL:
        move_type = CashMoveType.IN_

    amount = _money(request.form.get("amount"))
    if amount <= 0:
        flash("El monto debe ser mayor a 0.", "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

    note = (request.form.get("note") or "").strip() or None

    m = CashMovement(
        company_id=company_id,
        branch_id=branch_id,
        move_date=d,
        move_type=move_type,
        amount=amount,
        note=note,
        created_at=datetime.utcnow(),
    )
    db.session.add(m)
    db.session.commit()
    flash("Movimiento registrado.", "message")
    return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))
