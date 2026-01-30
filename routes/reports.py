from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, session, flash
from flask_login import login_required, current_user
from sqlalchemy import func, case

from models import db
from models.sale import Sale, SaleItem
from models.expense import Expense
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

    # Totales por método de pago (cash/transfer)
    agg_pay = db.session.query(
        func.coalesce(func.sum(case((Sale.payment_method == "cash", Sale.total), else_=0)), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "transfer", Sale.total), else_=0)), 0),
    ).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        agg_pay = agg_pay.filter(Sale.branch_id == selected_branch_id)

    cash_sum, transfer_sum = agg_pay.first()
    total_cash = Decimal(str(cash_sum or 0)).quantize(Decimal("0.01"))
    total_transfer = Decimal(str(transfer_sum or 0)).quantize(Decimal("0.01"))

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
        total_cash=float(total_cash),
        total_transfer=float(total_transfer),
    )


@reports_bp.get("/financial")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def financial_report():
    """Reporte financiero unificado (ventas + costos + gastos + balance)."""
    company_id = _company_id()
    current_branch_id = _branch_id()
    role = _get_role_in_context(company_id, current_branch_id)

    today = datetime.now()
    default_from = (today - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    default_to = today.replace(hour=0, minute=0, second=0, microsecond=0)

    date_from = _parse_date(request.args.get("from"), default_from)
    date_to = _parse_date(request.args.get("to"), default_to)
    date_to_end = date_to + timedelta(days=1)

    # Filtro sucursal
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
                    )
                    .first()
                )
                if not ok:
                    flash("Sucursal inválida para filtrar. Mostrando todas.", "error")
                    selected_branch_id = None

    # Filtro método pago
    pm = (request.args.get("payment_method") or "all").strip().lower()
    if pm not in ("all", "cash", "transfer"):
        pm = "all"

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

    # Base ventas
    q_sales = db.session.query(Sale).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        q_sales = q_sales.filter(Sale.branch_id == selected_branch_id)
    if pm != "all":
        q_sales = q_sales.filter(Sale.payment_method == pm)

    sales = q_sales.order_by(Sale.created_at.desc()).limit(200).all()

    # Totales ventas
    agg_sales = db.session.query(
        func.coalesce(func.sum(Sale.total), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "cash", Sale.total), else_=0)), 0),
        func.coalesce(func.sum(case((Sale.payment_method == "transfer", Sale.total), else_=0)), 0),
        func.count(Sale.id),
    ).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        agg_sales = agg_sales.filter(Sale.branch_id == selected_branch_id)
    if pm != "all":
        agg_sales = agg_sales.filter(Sale.payment_method == pm)

    total_sum, cash_sum, transfer_sum, total_count = agg_sales.first()

    # Costos y ganancia bruta (incluye descuento por item)
    profit_expr = ((SaleItem.unit_price - SaleItem.unit_cost) * SaleItem.qty) - func.coalesce(SaleItem.discount, 0)
    agg_cost_profit = db.session.query(
        func.coalesce(func.sum(SaleItem.unit_cost * SaleItem.qty), 0),
        func.coalesce(func.sum(profit_expr), 0),
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.company_id == company_id,
        Sale.created_at >= date_from,
        Sale.created_at < date_to_end,
    )
    if selected_branch_id is not None:
        agg_cost_profit = agg_cost_profit.filter(Sale.branch_id == selected_branch_id)
    if pm != "all":
        agg_cost_profit = agg_cost_profit.filter(Sale.payment_method == pm)

    total_cost_sum, total_profit_sum = agg_cost_profit.first()

    # Gastos por rango (Expense usa date)
    exp_q = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == company_id,
        Expense.expense_date >= date_from.date(),
        Expense.expense_date <= date_to.date(),
    )
    if selected_branch_id is not None:
        exp_q = exp_q.filter(Expense.branch_id == selected_branch_id)

    total_expenses_sum = exp_q.scalar() or 0

    total_amount = Decimal(str(total_sum or 0)).quantize(Decimal("0.01"))
    total_cash = Decimal(str(cash_sum or 0)).quantize(Decimal("0.01"))
    total_transfer = Decimal(str(transfer_sum or 0)).quantize(Decimal("0.01"))
    total_cost = Decimal(str(total_cost_sum or 0)).quantize(Decimal("0.01"))
    gross_profit = Decimal(str(total_profit_sum or 0)).quantize(Decimal("0.01"))
    total_expenses = Decimal(str(total_expenses_sum or 0)).quantize(Decimal("0.01"))
    net_profit = (gross_profit - total_expenses).quantize(Decimal("0.01"))

    return render_template(
        "reports_financial.html",
        branches=branches,
        selected_branch_id=(selected_branch_id or 0),
        role=role,
        date_from=date_from.strftime("%Y-%m-%d"),
        date_to=date_to.strftime("%Y-%m-%d"),
        payment_method=pm,
        sales=sales,
        total_count=int(total_count or 0),
        total_amount=float(total_amount),
        total_cash=float(total_cash),
        total_transfer=float(total_transfer),
        total_cost=float(total_cost),
        gross_profit=float(gross_profit),
        total_expenses=float(total_expenses),
        net_profit=float(net_profit),
    )

# =========================
# ADMIN: editar / eliminar ventas
# =========================

from decimal import InvalidOperation

from flask import redirect, url_for

from models.product import Product
from models.client import Client
from models.inventory import LocationType
from models.kardex import KardexMoveType
from services.stock import add_stock, remove_stock


def _to_decimal(val, q='0.01') -> Decimal:
    s = (str(val) if val is not None else '').strip().replace(',', '.')
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        d = Decimal('0')
    return d.quantize(Decimal(q))


def _default_unit_price(p: Product, price_mode: str) -> Decimal:
    mode = (price_mode or 'minorista').lower()
    if mode == 'mayorista':
        return _to_decimal(getattr(p, 'price_mayorista', 0) or 0)
    if mode == 'especial':
        return _to_decimal(getattr(p, 'price_especial', 0) or 0)
    return _to_decimal(getattr(p, 'price_minorista', 0) or 0)


@reports_bp.get('/sales/<int:sale_id>/edit')
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def sale_edit_view(sale_id: int):
    company_id = _company_id()

    sale = (
        db.session.query(Sale)
        .filter(Sale.id == sale_id, Sale.company_id == company_id)
        .first()
    )
    if not sale:
        flash('Venta no encontrada.', 'error')
        return redirect(url_for('reports.sales_list'))

    # Productos para agregar (limit para offline)
    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .order_by(Product.name.asc())
        .limit(700)
        .all()
    )

    client = None
    if sale.client_id:
        client = (
            db.session.query(Client)
            .filter(Client.id == sale.client_id, Client.company_id == company_id)
            .first()
        )

    return render_template(
        'reports_sale_edit.html',
        sale=sale,
        client=client,
        products=products,
    )


@reports_bp.post('/sales/<int:sale_id>/edit')
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def sale_edit_submit(sale_id: int):
    company_id = _company_id()

    sale: Sale | None = (
        db.session.query(Sale)
        .filter(Sale.id == sale_id, Sale.company_id == company_id)
        .first()
    )
    if not sale:
        flash('Venta no encontrada.', 'error')
        return redirect(url_for('reports.sales_list'))

    # Seguridad: la edición afecta inventario en la sucursal original de la venta
    branch_id = int(sale.branch_id)

    payment_method = (request.form.get('payment_method') or sale.payment_method or 'cash').strip().lower()
    if payment_method not in ('cash', 'transfer'):
        payment_method = 'cash'

    # Construir nuevo estado de items
    # Form fields por item:
    # qty_<sale_item_id>, price_<sale_item_id>, remove_<sale_item_id>
    # Nuevos items: new_product_id[], new_qty[], new_price[]

    try:
        # Snapshot actual
        old_items = {it.id: it for it in sale.items}

        # 1) Actualizar items existentes
        new_item_state: dict[int, dict] = {}
        for it_id, it in old_items.items():
            if request.form.get(f'remove_{it_id}') == '1':
                new_qty = Decimal('0.000')
            else:
                new_qty = _to_decimal(request.form.get(f'qty_{it_id}') or it.qty, q='0.001')
            new_price = _to_decimal(request.form.get(f'price_{it_id}') or it.unit_price, q='0.01')

            if new_qty < 0:
                new_qty = Decimal('0.000')

            new_item_state[it_id] = {
                'product_id': int(it.product_id),
                'qty': new_qty,
                'unit_price': new_price,
                'unit_cost': _to_decimal(it.unit_cost or 0, q='0.01'),
            }

        # 2) Agregar nuevos items
        new_products = request.form.getlist('new_product_id')
        new_qtys = request.form.getlist('new_qty')
        new_prices = request.form.getlist('new_price')

        for idx, pid_raw in enumerate(new_products):
            pid_raw = (pid_raw or '').strip()
            if not pid_raw:
                continue
            try:
                pid = int(pid_raw)
            except ValueError:
                continue

            qty_raw = new_qtys[idx] if idx < len(new_qtys) else '0'
            price_raw = new_prices[idx] if idx < len(new_prices) else ''

            qty = _to_decimal(qty_raw, q='0.001')
            if qty <= 0:
                continue

            p = db.session.get(Product, pid)
            if not p or p.company_id != company_id or not p.is_active:
                raise ValueError('Producto inválido al agregar.')

            if str(price_raw).strip() == '':
                unit_price = _default_unit_price(p, sale.price_mode)
            else:
                unit_price = _to_decimal(price_raw, q='0.01')

            db.session.add(SaleItem(
                sale_id=sale.id,
                product_id=pid,
                qty=qty,
                unit_price=unit_price,
                unit_cost=_to_decimal(getattr(p, 'cost_price', 0) or 0, q='0.01'),
                discount=Decimal('0.00'),
                subtotal=(qty * unit_price).quantize(Decimal('0.01')),
            ))

            # Ajuste inventario (salió más por edición)
            remove_stock(
                db.session,
                company_id=company_id,
                product_id=pid,
                location_type=LocationType.BRANCH,
                location_id=branch_id,
                qty=qty,
                move_type=KardexMoveType.SALE_EDIT,
                note=f'Edición venta #{sale.id}: +{qty} (agregado)',
            )

        db.session.flush()

        # 3) Aplicar cambios en items existentes (inventario + valores)
        for it_id, it in old_items.items():
            st = new_item_state[it_id]
            new_qty = st['qty']
            new_price = st['unit_price']

            old_qty = _to_decimal(it.qty, q='0.001')
            delta = (new_qty - old_qty).quantize(Decimal('0.001'))

            # Inventario según delta
            if delta > 0:
                # se vendió más -> restar stock adicional
                remove_stock(
                    db.session,
                    company_id=company_id,
                    product_id=int(it.product_id),
                    location_type=LocationType.BRANCH,
                    location_id=branch_id,
                    qty=delta,
                    move_type=KardexMoveType.SALE_EDIT,
                    note=f'Edición venta #{sale.id}: +{delta}',
                )
            elif delta < 0:
                # se vendió menos -> devolver stock
                add_stock(
                    db.session,
                    company_id=company_id,
                    product_id=int(it.product_id),
                    location_type=LocationType.BRANCH,
                    location_id=branch_id,
                    qty=(-delta),
                    move_type=KardexMoveType.SALE_EDIT,
                    note=f'Edición venta #{sale.id}: {delta} (devolución)',
                )

            # Actualizar o eliminar item
            if new_qty <= 0:
                db.session.delete(it)
            else:
                it.qty = new_qty
                it.unit_price = new_price
                it.subtotal = (new_qty * new_price).quantize(Decimal('0.01'))

        db.session.flush()

        # 4) Recalcular totales
        refreshed_items = (
            db.session.query(SaleItem)
            .filter(SaleItem.sale_id == sale.id)
            .all()
        )

        subtotal = Decimal('0.00')
        for it in refreshed_items:
            subtotal += _to_decimal(it.subtotal, q='0.01')

        sale.payment_method = payment_method
        sale.subtotal = subtotal.quantize(Decimal('0.01'))
        sale.discount_total = Decimal('0.00')
        sale.total = subtotal.quantize(Decimal('0.01'))

        db.session.commit()
        flash(f'✅ Venta #{sale.id} actualizada y registrada en Kardex.', 'message')
        return redirect(url_for('reports.sales_list'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al editar venta: {e}', 'error')
        return redirect(url_for('reports.sale_edit_view', sale_id=sale_id))


@reports_bp.post('/sales/<int:sale_id>/delete')
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def sale_delete(sale_id: int):
    company_id = _company_id()

    sale: Sale | None = (
        db.session.query(Sale)
        .filter(Sale.id == sale_id, Sale.company_id == company_id)
        .first()
    )
    if not sale:
        flash('Venta no encontrada.', 'error')
        return redirect(url_for('reports.sales_list'))

    branch_id = int(sale.branch_id)

    try:
        # Devolver stock de todos los items
        for it in list(sale.items):
            qty = _to_decimal(it.qty, q='0.001')
            if qty > 0:
                add_stock(
                    db.session,
                    company_id=company_id,
                    product_id=int(it.product_id),
                    location_type=LocationType.BRANCH,
                    location_id=branch_id,
                    qty=qty,
                    move_type=KardexMoveType.SALE_VOID,
                    note=f'Anulación venta #{sale.id}: devolución {qty}',
                )

        # Eliminar venta (cascade elimina items)
        db.session.delete(sale)
        db.session.commit()

        flash('✅ Venta eliminada. Inventario devuelto y Kardex registrado.', 'message')
        return redirect(url_for('reports.sales_list'))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar venta: {e}', 'error')
        return redirect(url_for('reports.sales_list'))
