from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required
from sqlalchemy import func

from models import db
from models.product import Product
from models.company import Company
from models.branch import Branch
from models.client import Client
from models.membership import Role
from models.sale import Sale, SaleItem
from models.inventory import LocationType
from models.kardex import KardexMoveType
from routes.guards import require_context, require_roles

from services.stock import remove_stock

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


def _company_id() -> int:
    return int(session["company_id"])


def _branch_id() -> int:
    return int(session["branch_id"])


def _get_cart() -> dict:
    cart = session.get("pos_cart")
    if not cart or not isinstance(cart, dict):
        cart = {
            "price_mode": "minorista",  # minorista | mayorista | especial
            "client_id": None,
            "client_name": None,
            # items: {product_id, name, qty, unit_price, subtotal, image_path?, image_v?}
            "items": []
        }
        session["pos_cart"] = cart

    cart.setdefault("price_mode", "minorista")
    cart.setdefault("client_id", None)
    cart.setdefault("client_name", None)
    cart.setdefault("items", [])
    return cart


def _save_cart(cart: dict) -> None:
    session["pos_cart"] = cart
    session.modified = True


def _price_for_mode(product: Product, mode: str) -> Decimal:
    mode = (mode or "minorista").lower()
    if mode == "mayorista":
        return Decimal(str(product.price_mayorista))
    if mode == "especial":
        return Decimal(str(product.price_especial))
    return Decimal(str(product.price_minorista))


def _recalc(cart: dict) -> None:
    total = Decimal("0.00")
    for it in cart["items"]:
        it["subtotal"] = float(Decimal(str(it["qty"])) * Decimal(str(it["unit_price"])))
        total += Decimal(str(it["subtotal"]))
    cart["total"] = float(total)


def _apply_price_mode_to_items(cart: dict) -> None:
    company_id = _company_id()
    mode = cart.get("price_mode", "minorista")

    for it in cart["items"]:
        p = db.session.get(Product, int(it["product_id"]))
        if p and p.company_id == company_id and p.is_active:
            it["unit_price"] = float(_price_for_mode(p, mode))

    _recalc(cart)


def _get_quick_products(company_id: int, branch_id: int, limit: int = 10):
    """
    Top productos más vendidos por sucursal (últimos 30 días).
    Fallback: últimos productos creados si no hay ventas.
    """
    since = datetime.utcnow() - timedelta(days=30)

    rows = (
        db.session.query(Product)
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Product.company_id == company_id,
            Product.is_active == True,
            Sale.company_id == company_id,
            Sale.branch_id == branch_id,
            Sale.created_at >= since
        )
        .group_by(Product.id)
        .order_by(func.sum(SaleItem.qty).desc())
        .limit(limit)
        .all()
    )

    if rows:
        return rows

    # Fallback: si aún no hay ventas
    return (
        db.session.query(Product)
        .filter(Product.company_id == company_id, Product.is_active == True)
        .order_by(Product.id.desc())
        .limit(limit)
        .all()
    )


@pos_bp.get("/sale")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def sale():
    company_id = _company_id()
    branch_id = _branch_id()

    cart = _get_cart()
    _recalc(cart)
    _save_cart(cart)

    quick_products = _get_quick_products(company_id, branch_id, limit=10)

    return render_template("pos_sale.html", cart=cart, quick_products=quick_products)


@pos_bp.post("/cart/clear")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_clear():
    session.pop("pos_cart", None)
    flash("Carrito limpio.", "message")
    return redirect(url_for("pos.sale"))


@pos_bp.post("/cart/set-client")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_set_client():
    company_id = _company_id()
    cart = _get_cart()

    client_id_raw = (request.form.get("client_id") or "").strip()

    # Quitar cliente
    if client_id_raw == "" or client_id_raw == "0":
        cart["client_id"] = None
        cart["client_name"] = None
        cart["price_mode"] = "minorista"
        _apply_price_mode_to_items(cart)
        _save_cart(cart)
        flash("Cliente removido. Precio vuelto a Minorista.", "message")
        return redirect(url_for("pos.sale"))

    try:
        client_id = int(client_id_raw)
    except ValueError:
        flash("Cliente inválido.", "error")
        return redirect(url_for("pos.sale"))

    client = (
        db.session.query(Client)
        .filter(
            Client.id == client_id,
            Client.company_id == company_id,
            Client.is_active == True
        )
        .first()
    )
    if not client:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("pos.sale"))

    cart["client_id"] = client.id
    cart["client_name"] = client.full_name

    # Auto price mode por tipo de cliente (debe existir client.price_mode en tu modelo)
    cart["price_mode"] = client.price_mode

    _apply_price_mode_to_items(cart)
    _save_cart(cart)

    flash(f"Cliente seleccionado: {client.full_name} ({client.client_type})", "message")
    return redirect(url_for("pos.sale"))


@pos_bp.post("/cart/set-price-mode")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_set_price_mode():
    mode = (request.form.get("price_mode") or "minorista").lower()
    if mode not in ("minorista", "mayorista", "especial"):
        flash("Tipo de precio inválido.", "error")
        return redirect(url_for("pos.sale"))

    cart = _get_cart()
    cart["price_mode"] = mode
    _apply_price_mode_to_items(cart)
    _save_cart(cart)

    flash("Tipo de precio actualizado.", "message")
    return redirect(url_for("pos.sale"))


@pos_bp.post("/cart/add")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_add():
    company_id = _company_id()
    cart = _get_cart()

    product_id = request.form.get("product_id")
    query = (request.form.get("query") or "").strip()

    product = None
    if product_id:
        product = db.session.get(Product, int(product_id))
        if not product or product.company_id != company_id or not product.is_active:
            flash("Producto inválido.", "error")
            return redirect(url_for("pos.sale"))
    else:
        if not query:
            flash("Ingresa un SKU o Barcode.", "error")
            return redirect(url_for("pos.sale"))

        product = (
            db.session.query(Product)
            .filter(
                Product.company_id == company_id,
                Product.is_active == True,
                (Product.barcode == query) | (Product.sku == query)
            )
            .first()
        )

        if not product:
            product = (
                db.session.query(Product)
                .filter(
                    Product.company_id == company_id,
                    Product.is_active == True,
                    Product.name.ilike(f"%{query}%")
                )
                .order_by(Product.name.asc())
                .first()
            )

        if not product:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("pos.sale"))

    mode = cart.get("price_mode", "minorista")
    unit_price = float(_price_for_mode(product, mode))

    # Cache-buster para imagen (si la imagen se actualiza, el navegador
    # no se queda con la versión vieja).
    image_v = 1
    if getattr(product, "image_updated_at", None):
        try:
            image_v = int(product.image_updated_at.timestamp())
        except Exception:
            image_v = 1

    for it in cart["items"]:
        if int(it["product_id"]) == int(product.id):
            it["qty"] = int(it["qty"]) + 1
            it["unit_price"] = unit_price
            # Si el producto tenía imagen y el carrito fue creado antes,
            # rellenamos para evitar que salga sin foto.
            it.setdefault("image_path", product.image_path)
            it.setdefault("image_v", image_v)
            _recalc(cart)
            _save_cart(cart)
            return redirect(url_for("pos.sale"))

    cart["items"].append({
        "product_id": int(product.id),
        "name": product.name,
        "qty": 1,
        "unit_price": unit_price,
        "subtotal": unit_price,
        "image_path": product.image_path,
        "image_v": image_v,
    })
    _recalc(cart)
    _save_cart(cart)
    return redirect(url_for("pos.sale"))


@pos_bp.post("/cart/update-qty")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_update_qty():
    product_id = int(request.form.get("product_id") or 0)
    qty = int(request.form.get("qty") or 1)
    if qty < 1:
        qty = 1

    cart = _get_cart()
    for it in cart["items"]:
        if int(it["product_id"]) == product_id:
            it["qty"] = qty
            break

    _recalc(cart)
    _save_cart(cart)
    return redirect(url_for("pos.sale"))


@pos_bp.post("/cart/remove")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def cart_remove():
    product_id = int(request.form.get("product_id") or 0)
    cart = _get_cart()
    cart["items"] = [it for it in cart["items"] if int(it["product_id"]) != product_id]
    _recalc(cart)
    _save_cart(cart)
    return redirect(url_for("pos.sale"))


@pos_bp.post("/checkout")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def checkout():
    company_id = _company_id()
    branch_id = _branch_id()
    cart = _get_cart()
    _recalc(cart)

    items = cart.get("items", [])
    if not items:
        flash("Carrito vacío.", "error")
        return redirect(url_for("pos.sale"))

    price_mode = cart.get("price_mode", "minorista")
    client_id = cart.get("client_id")

    payment_method = (request.form.get("payment_method") or "cash").strip().lower()
    if payment_method not in ("cash", "transfer"):
        payment_method = "cash"

    try:
        sale_total = Decimal(str(cart.get("total", 0))).quantize(Decimal("0.01"))

        # Validar cliente si viene
        if client_id:
            client = (
                db.session.query(Client)
                .filter(
                    Client.id == int(client_id),
                    Client.company_id == company_id,
                    Client.is_active == True
                )
                .first()
            )
            if not client:
                raise ValueError("Cliente inválido (ya no existe o está inactivo).")

        sale = Sale(
            company_id=company_id,
            branch_id=branch_id,
            client_id=(int(client_id) if client_id else None),
            price_mode=price_mode,
            subtotal=sale_total,
            discount_total=Decimal("0.00"),
            total=sale_total,
            payment_method=payment_method,
        )
        db.session.add(sale)
        db.session.flush()

        for it in items:
            product_id = int(it["product_id"])
            qty = Decimal(str(it["qty"])).quantize(Decimal("0.001"))
            unit_price = Decimal(str(it["unit_price"])).quantize(Decimal("0.01"))
            subtotal = Decimal(str(it["subtotal"])).quantize(Decimal("0.01"))

            p = db.session.get(Product, product_id)
            if not p or p.company_id != company_id or not p.is_active:
                raise ValueError(f"Producto inválido en carrito (id={product_id}).")

            remove_stock(
                db.session,
                company_id=company_id,
                product_id=product_id,
                location_type=LocationType.BRANCH,
                location_id=branch_id,
                qty=qty,
                move_type=KardexMoveType.SALE_OUT,
                note=f"Venta #{sale.id}",
            )

            db.session.add(SaleItem(
                sale_id=sale.id,
                product_id=product_id,
                qty=qty,
                unit_price=unit_price,
                unit_cost=Decimal(str(getattr(p, "cost_price", 0) or 0)).quantize(Decimal("0.01")),
                discount=Decimal("0.00"),
                subtotal=subtotal,
            ))

        db.session.commit()
        session.pop("pos_cart", None)
        flash(f"✅ Venta #{sale.id} registrada.", "message")
        return redirect(url_for("pos.ticket", sale_id=sale.id))

    except Exception as e:
        db.session.rollback()
        flash(f"Error al finalizar venta: {e}", "error")
        return redirect(url_for("pos.sale"))


@pos_bp.get("/ticket/<int:sale_id>")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def ticket(sale_id: int):
    company_id = _company_id()

    sale = (
        db.session.query(Sale)
        .filter(Sale.id == sale_id, Sale.company_id == company_id)
        .first()
    )
    if not sale:
        flash("Venta no encontrada.", "error")
        return redirect(url_for("pos.sale"))

    company = db.session.get(Company, int(sale.company_id))
    branch = db.session.get(Branch, int(sale.branch_id))

    client = None
    if sale.client_id:
        client = (
            db.session.query(Client)
            .filter(
                Client.id == int(sale.client_id),
                Client.company_id == company_id,
                Client.is_active == True
            )
            .first()
        )

    return render_template(
        "pos_ticket.html",
        sale=sale,
        company=company,
        branch=branch,
        client=client
    )


@pos_bp.get("/search")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def search():
    company_id = _company_id()
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    products = (
        db.session.query(Product)
        .filter(
            Product.company_id == company_id,
            Product.is_active == True,
            (Product.name.ilike(f"%{q}%")) | (Product.sku.ilike(f"%{q}%")) | (Product.barcode.ilike(f"%{q}%"))
        )
        .order_by(Product.name.asc())
        .limit(10)
        .all()
    )

    return jsonify([{"id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode} for p in products])
