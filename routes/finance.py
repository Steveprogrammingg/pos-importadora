from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import login_required
from sqlalchemy.exc import OperationalError

from models import db
from models.cash_movement import CashMovement, CashMoveType
from models.cash_count import CashCount
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




def _friendly_db_error(e: Exception) -> str:
    msg = str(e).lower()
    if "no such table" in msg or "does not exist" in msg:
        return "Base de datos no inicializada o migraciones pendientes. Ejecuta: flask db upgrade"
    return "Error de base de datos. Revisa logs/app.log"
def _money(v: str | None) -> Decimal:
    try:
        return Decimal((v or "0").replace(",", "."))
    except Exception:
        return Decimal("0")


@finance_bp.get("/")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
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

    sales_cash_total = sum(Decimal(str(s.total)) for s in sales_last7 if (getattr(s, 'payment_method', 'cash') or 'cash') == 'cash')
    sales_transfer_total = sum(Decimal(str(s.total)) for s in sales_last7 if (getattr(s, 'payment_method', 'cash') or 'cash') == 'transfer')

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
        sales_cash_total=float(sales_cash_total),
        sales_transfer_total=float(sales_transfer_total),
        today=today,
    )


@finance_bp.get("/expenses")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
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
@require_roles(Role.ADMIN, Role.OWNER)
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
@require_roles(Role.ADMIN, Role.OWNER)
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
@require_roles(Role.ADMIN, Role.OWNER)
def cash_dashboard():
    """Dashboard de Caja (movimientos del día por sucursal)."""
    try:
        company_id, branch_id = _ctx_ids()
        today = date.today()
        d = _as_date(request.args.get("d"), today)

        moves = (
            db.session.query(CashMovement)
            .filter(
                CashMovement.company_id == company_id,
                CashMovement.branch_id == branch_id,
                CashMovement.move_date == d,
            )
            .order_by(CashMovement.id.desc())
            .all()
        )

        # Apertura de caja (un IN con nota "APERTURA")
        opening = next((m for m in reversed(moves) if m.move_type == CashMoveType.IN_ and (m.note or '').strip().upper() == 'APERTURA'), None)
        opening_amount = Decimal(str(opening.amount)) if opening else Decimal('0')

        # Conteo (efectivo contado)
        cash_count = (
            db.session.query(CashCount)
            .filter(CashCount.company_id == company_id, CashCount.branch_id == branch_id, CashCount.count_date == d)
            .one_or_none()
        )
        counted_amount = Decimal(str(cash_count.amount_counted)) if cash_count else None

        # Ventas del día (por método de pago)
        from models.sale import Sale
        start_dt = datetime.combine(d, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        sales_day = (
            db.session.query(Sale)
            .filter(
                Sale.company_id == company_id,
                Sale.branch_id == branch_id,
                Sale.created_at >= start_dt,
                Sale.created_at < end_dt,
            )
            .all()
        )
        sales_total = sum(Decimal(str(s.total)) for s in sales_day)
        sales_cash = sum(Decimal(str(s.total)) for s in sales_day if (getattr(s, 'payment_method', 'cash') or 'cash') == 'cash')
        sales_transfer = sum(Decimal(str(s.total)) for s in sales_day if (getattr(s, 'payment_method', 'cash') or 'cash') == 'transfer')

        # Movimientos manuales del día (excluye apertura para cálculos de efectivo esperado)
        manual_moves = [m for m in moves if not (m.id == (opening.id if opening else -1))]
        total_in = sum(Decimal(str(m.amount)) for m in manual_moves if m.move_type == CashMoveType.IN_)
        total_out = sum(Decimal(str(m.amount)) for m in manual_moves if m.move_type == CashMoveType.OUT)
        net = total_in - total_out

        expected_cash = opening_amount + sales_cash + total_in - total_out
        diff = (counted_amount - expected_cash) if counted_amount is not None else None

        return render_template(
            "finance_cash_dashboard.html",
            d=d,
            moves=moves,
            opening=opening,
            opening_amount=float(opening_amount),
            cash_count=cash_count,
            counted_amount=float(counted_amount) if counted_amount is not None else None,
            diff=float(diff) if diff is not None else None,
            expected_cash=float(expected_cash),
            sales_total=float(sales_total),
            sales_cash=float(sales_cash),
            sales_transfer=float(sales_transfer),
            total_in=float(total_in),
            total_out=float(total_out),
            net=float(net),
            move_types=[CashMoveType.IN_, CashMoveType.OUT],
        )

    except OperationalError as e:
        db.session.rollback()
        flash(_friendly_db_error(e), "error")
        return redirect(url_for("finance.dashboard"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error en cash_dashboard")
        flash("Ocurrió un error al cargar Caja. Revisa logs/app.log.", "error")
        return redirect(url_for("finance.dashboard"))


@finance_bp.post("/cash/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def cash_new_post():
    """Crear un movimiento de Caja (Ingreso/Egreso)."""
    d = _as_date(request.form.get("move_date"), date.today())

    try:
        company_id, branch_id = _ctx_ids()

        move_type = (request.form.get("move_type") or CashMoveType.IN_).strip().upper()
        if move_type not in CashMoveType.ALL:
            move_type = CashMoveType.IN_

        amount = _money(request.form.get("amount"))
        if amount <= 0:
            flash("El monto debe ser mayor a 0.", "error")
            return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

        note = (request.form.get("note") or "").strip() or None

        # Evitar que el usuario cree manualmente una "APERTURA" desde este formulario
        if note and note.strip().upper() == 'APERTURA':
            flash("La apertura se registra desde el botón 'Abrir Caja'.", "error")
            return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

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

    except OperationalError as e:
        db.session.rollback()
        flash(_friendly_db_error(e), "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en cash_new_post")
        flash("Ocurrió un error al registrar el movimiento. Revisa logs/app.log.", "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))


@finance_bp.post("/cash/open")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def cash_open_post():
    """Registrar apertura de caja (monto inicial) para un día.

    Se guarda como un movimiento IN con nota "APERTURA".
    Solo se permite una apertura por día/sucursal.
    """
    d = _as_date(request.form.get("move_date"), date.today())
    try:
        company_id, branch_id = _ctx_ids()
        amount = _money(request.form.get("opening_amount"))
        if amount < 0:
            flash("El monto inicial no puede ser negativo.", "error")
            return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

        existing = (
            db.session.query(CashMovement)
            .filter(
                CashMovement.company_id == company_id,
                CashMovement.branch_id == branch_id,
                CashMovement.move_date == d,
                CashMovement.move_type == CashMoveType.IN_,
                CashMovement.note.ilike('APERTURA'),
            )
            .first()
        )
        if existing:
            flash("La caja ya tiene apertura registrada para este día.", "error")
            return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

        m = CashMovement(
            company_id=company_id,
            branch_id=branch_id,
            move_date=d,
            move_type=CashMoveType.IN_,
            amount=amount,
            note="APERTURA",
            created_at=datetime.utcnow(),
        )
        db.session.add(m)
        db.session.commit()
        flash("Apertura registrada.", "message")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

    except OperationalError as e:
        db.session.rollback()
        flash(_friendly_db_error(e), "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en cash_open_post")
        flash("Ocurrió un error al registrar la apertura. Revisa logs/app.log.", "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))


@finance_bp.post("/cash/count")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def cash_count_post():
    """Guardar/actualizar el efectivo contado del día."""
    d = _as_date(request.form.get("count_date"), date.today())
    try:
        company_id, branch_id = _ctx_ids()
        amount = _money(request.form.get("counted_amount"))
        if amount < 0:
            flash("El efectivo contado no puede ser negativo.", "error")
            return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

        note = (request.form.get("note") or "").strip() or None

        cc = (
            db.session.query(CashCount)
            .filter(CashCount.company_id == company_id, CashCount.branch_id == branch_id, CashCount.count_date == d)
            .one_or_none()
        )
        if cc:
            cc.amount_counted = amount
            cc.note = note
        else:
            cc = CashCount(
                company_id=company_id,
                branch_id=branch_id,
                count_date=d,
                amount_counted=amount,
                note=note,
                created_at=datetime.utcnow(),
            )
            db.session.add(cc)

        db.session.commit()
        flash("Conteo guardado.", "message")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

    except OperationalError as e:
        db.session.rollback()
        flash(_friendly_db_error(e), "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error en cash_count_post")
        flash("Ocurrió un error al guardar el conteo. Revisa logs/app.log.", "error")
        return redirect(url_for("finance.cash_dashboard", d=d.strftime("%Y-%m-%d")))

