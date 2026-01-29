import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required
from werkzeug.utils import secure_filename

from models import db
from models.user import User
from models.branch import Branch
from models.membership import CompanyUser, Role
from models.product import Product
from models.inventory import Inventory, LocationType
from routes.guards import require_context, require_roles

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# -------------------------
# Helpers
# -------------------------
# -------------------------
# Upload helpers (imágenes)
# -------------------------
_ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp"}

def _allowed_image(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in _ALLOWED_IMAGE_EXT

def _company_id() -> int:
    return int(session["company_id"])


def _clean_str(value: str | None) -> str:
    return (value or "").strip()


def _to_int(val: str | None, default: int = 0) -> int:
    try:
        return int((val or "").strip())
    except ValueError:
        return default


def _to_decimal(val: str | None) -> Decimal:
    """
    Convierte string a Decimal(12,2) seguro.
    - Acepta coma o punto.
    - No permite negativos.
    - Si falla -> 0.00
    """
    raw = _clean_str(val).replace(",", ".")
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
    if d < 0:
        return Decimal("0.00")
    return d.quantize(Decimal("0.01"))


# =========================
# USUARIOS (Admin empresa)
# =========================
@admin_bp.get("/users")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_list():
    company_id = _company_id()

    memberships = (
        db.session.query(CompanyUser)
        .filter(
            CompanyUser.company_id == company_id
        )
        .all()
    )
    return render_template("admin_users.html", memberships=memberships)


@admin_bp.get("/users/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_new_get():
    company_id = _company_id()
    branches = (
        db.session.query(Branch)
        .filter(
            Branch.company_id == company_id,
            Branch.is_active == True
        )
        .order_by(Branch.is_warehouse.desc(), Branch.name.asc())
        .all()
    )
    return render_template("admin_user_new.html", branches=branches)


@admin_bp.post("/users/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_new_post():
    company_id = _company_id()

    full_name = _clean_str(request.form.get("full_name"))
    email = _clean_str(request.form.get("email")).lower()
    password = request.form.get("password") or ""
    role = _clean_str(request.form.get("role"))
    branch_id_raw = _clean_str(request.form.get("branch_id"))

    if not full_name or not email or not password:
        flash("Nombre, email y contraseña son obligatorios.", "error")
        return redirect(url_for("admin.users_new_get"))

    if role not in Role.ALL:
        flash("Rol inválido.", "error")
        return redirect(url_for("admin.users_new_get"))

    branch_id_int = int(branch_id_raw) if branch_id_raw else None
    if role == Role.SELLER and not branch_id_int:
        flash("Un vendedor debe tener una sucursal asignada.", "error")
        return redirect(url_for("admin.users_new_get"))

    if branch_id_int:
        b = (
            db.session.query(Branch)
            .filter(
                Branch.id == branch_id_int,
                Branch.company_id == company_id,
                Branch.is_active == True
            )
            .first()
        )
        if not b:
            flash("Sucursal inválida para esta empresa.", "error")
            return redirect(url_for("admin.users_new_get"))

    user = db.session.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
    else:
        user.full_name = full_name

    membership_branch_id = branch_id_int if role in (Role.SELLER, Role.SUPERVISOR) else None

    exists = (
        db.session.query(CompanyUser)
        .filter_by(
            user_id=user.id,
            company_id=company_id,
            branch_id=membership_branch_id
        )
        .first()
    )
    if exists:
        flash("Este usuario ya tiene permisos asignados en esta empresa/sucursal.", "error")
        db.session.rollback()
        return redirect(url_for("admin.users_list"))

    membership = CompanyUser(
        user_id=user.id,
        company_id=company_id,
        branch_id=membership_branch_id,
        role=role,
        is_active=True
    )
    db.session.add(membership)
    db.session.commit()

    flash("Usuario creado y permisos asignados.", "message")
    return redirect(url_for("admin.users_list"))



@admin_bp.post("/users/<int:membership_id>/toggle-active")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_toggle_membership(membership_id: int):
    """Activa/Desactiva el acceso del usuario a la empresa (CompanyUser)."""
    company_id = _company_id()
    m = (
        db.session.query(CompanyUser)
        .filter(CompanyUser.id == membership_id, CompanyUser.company_id == company_id)
        .first()
    )
    if not m:
        flash("Membresía no encontrada.", "error")
        return redirect(url_for("admin.users_list"))

    m.is_active = not bool(m.is_active)
    db.session.commit()
    flash("Permiso actualizado (activo/inactivo).", "message")
    return redirect(url_for("admin.users_list"))


@admin_bp.get("/users/<int:membership_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_edit_get(membership_id: int):
    company_id = _company_id()
    m = (
        db.session.query(CompanyUser)
        .filter(CompanyUser.id == membership_id, CompanyUser.company_id == company_id)
        .first()
    )
    if not m:
        flash("Membresía no encontrada.", "error")
        return redirect(url_for("admin.users_list"))

    branches = (
        db.session.query(Branch)
        .filter(
            Branch.company_id == company_id,
            Branch.is_active == True
        )
        .order_by(Branch.is_warehouse.desc(), Branch.name.asc())
        .all()
    )
    return render_template("admin_user_edit.html", membership=m, branches=branches)


@admin_bp.post("/users/<int:membership_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def users_edit_post(membership_id: int):
    company_id = _company_id()
    m = (
        db.session.query(CompanyUser)
        .filter(CompanyUser.id == membership_id, CompanyUser.company_id == company_id)
        .first()
    )
    if not m:
        flash("Membresía no encontrada.", "error")
        return redirect(url_for("admin.users_list"))

    full_name = _clean_str(request.form.get("full_name"))
    email = _clean_str(request.form.get("email")).lower()
    password = request.form.get("password") or ""
    role = _clean_str(request.form.get("role"))
    branch_id_raw = _clean_str(request.form.get("branch_id"))

    if not full_name or not email:
        flash("Nombre y email son obligatorios.", "error")
        return redirect(url_for("admin.users_edit_get", membership_id=membership_id))

    if role not in Role.ALL:
        flash("Rol inválido.", "error")
        return redirect(url_for("admin.users_edit_get", membership_id=membership_id))

    branch_id_int = int(branch_id_raw) if branch_id_raw else None
    if role == Role.SELLER and not branch_id_int:
        flash("Un vendedor debe tener una sucursal asignada.", "error")
        return redirect(url_for("admin.users_edit_get", membership_id=membership_id))

    if branch_id_int:
        b = (
            db.session.query(Branch)
            .filter(
                Branch.id == branch_id_int,
                Branch.company_id == company_id,
                Branch.is_active == True
            )
            .first()
        )
        if not b:
            flash("Sucursal inválida para esta empresa.", "error")
            return redirect(url_for("admin.users_edit_get", membership_id=membership_id))

    # Email único a nivel sistema (users.email)
    if email != m.user.email:
        exists_user = db.session.query(User).filter(User.email == email).first()
        if exists_user:
            flash("Ya existe un usuario con ese email.", "error")
            return redirect(url_for("admin.users_edit_get", membership_id=membership_id))
        m.user.email = email

    m.user.full_name = full_name
    if password.strip():
        m.user.set_password(password.strip())

    m.role = role
    m.branch_id = branch_id_int if role in (Role.SELLER, Role.SUPERVISOR) else None

    db.session.commit()
    flash("Usuario actualizado.", "message")
    return redirect(url_for("admin.users_list"))


# =========================
# PRODUCTOS (3 precios)
# =========================
@admin_bp.get("/products")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_list():
    company_id = _company_id()
    products = (
        db.session.query(Product)
        .filter(Product.company_id == company_id)
        .order_by(Product.is_active.desc(), Product.name.asc())
        .all()
    )
    return render_template("admin_products.html", products=products)


@admin_bp.get("/products/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_new_get():
    return render_template("admin_product_new.html")


@admin_bp.post("/products/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_new_post():
    company_id = _company_id()

    name = _clean_str(request.form.get("name"))
    sku = _clean_str(request.form.get("sku")) or None
    barcode = _clean_str(request.form.get("barcode")) or None

    p1 = _to_decimal(request.form.get("price_minorista"))
    p2 = _to_decimal(request.form.get("price_mayorista"))
    p3 = _to_decimal(request.form.get("price_especial"))

    if not name:
        flash("El nombre del producto es obligatorio.", "error")
        return redirect(url_for("admin.products_new_get"))

    if sku and db.session.query(Product).filter(Product.company_id == company_id, Product.sku == sku).first():
        flash("SKU ya existe en esta empresa.", "error")
        return redirect(url_for("admin.products_new_get"))

    if barcode and db.session.query(Product).filter(Product.company_id == company_id, Product.barcode == barcode).first():
        flash("Barcode ya existe en esta empresa.", "error")
        return redirect(url_for("admin.products_new_get"))

    product = Product(
        company_id=company_id,
        name=name,
        sku=sku,
        barcode=barcode,
        price_minorista=p1,
        price_mayorista=p2,
        price_especial=p3,
        is_active=True
    )
    db.session.add(product)
    db.session.commit()

    flash("Producto creado.", "message")
    return redirect(url_for("admin.products_list"))


@admin_bp.get("/products/<int:product_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_edit_get(product_id: int):
    company_id = _company_id()
    product = (
        db.session.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id)
        .first()
    )
    if not product:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("admin.products_list"))

    return render_template("admin_product_edit.html", product=product)


@admin_bp.post("/products/<int:product_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_edit_post(product_id: int):
    company_id = _company_id()
    product = (
        db.session.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id)
        .first()
    )
    if not product:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("admin.products_list"))

    name = _clean_str(request.form.get("name"))
    sku = _clean_str(request.form.get("sku")) or None
    barcode = _clean_str(request.form.get("barcode")) or None

    p1 = _to_decimal(request.form.get("price_minorista"))
    p2 = _to_decimal(request.form.get("price_mayorista"))
    p3 = _to_decimal(request.form.get("price_especial"))

    if not name:
        flash("El nombre del producto es obligatorio.", "error")
        return redirect(url_for("admin.products_edit_get", product_id=product_id))

    if sku:
        exists = (
            db.session.query(Product)
            .filter(
                Product.company_id == company_id,
                Product.sku == sku,
                Product.id != product.id
            )
            .first()
        )
        if exists:
            flash("SKU ya existe en esta empresa.", "error")
            return redirect(url_for("admin.products_edit_get", product_id=product_id))

    if barcode:
        exists = (
            db.session.query(Product)
            .filter(
                Product.company_id == company_id,
                Product.barcode == barcode,
                Product.id != product.id
            )
            .first()
        )
        if exists:
            flash("Barcode ya existe en esta empresa.", "error")
            return redirect(url_for("admin.products_edit_get", product_id=product_id))

    product.name = name
    product.sku = sku
    product.barcode = barcode
    product.price_minorista = p1
    product.price_mayorista = p2
    product.price_especial = p3

    db.session.commit()
    flash("Producto actualizado.", "message")
    return redirect(url_for("admin.products_list"))


@admin_bp.post("/products/<int:product_id>/upload-image")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def product_upload_image(product_id: int):
    company_id = _company_id()
    product = (
        db.session.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id)
        .first()
    )
    if not product:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("admin.products_list"))

    file = request.files.get("image")
    if not file or not file.filename:
        flash("Selecciona una imagen.", "error")
        return redirect(url_for("admin.products_edit_get", product_id=product_id))

    if not _allowed_image(file.filename):
        flash("Formato inválido. Usa png/jpg/jpeg/webp.", "error")
        return redirect(url_for("admin.products_edit_get", product_id=product_id))

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()

    # Guardar en static/uploads/products/
    upload_dir = os.path.join(admin_bp.root_path, "..", "static", "uploads", "products")
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)

    final_name = f"product_{product.id}.{ext}"
    save_path = os.path.join(upload_dir, final_name)
    file.save(save_path)

    product.image_path = f"uploads/products/{final_name}"
    product.image_updated_at = datetime.utcnow()
    db.session.commit()

    flash("Imagen actualizada.", "message")
    return redirect(url_for("admin.products_edit_get", product_id=product_id))



@admin_bp.post("/products/<int:product_id>/toggle-active")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def products_toggle_active(product_id: int):
    company_id = _company_id()
    product = (
        db.session.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id)
        .first()
    )
    if not product:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("admin.products_list"))

    product.is_active = not bool(product.is_active)
    db.session.commit()

    flash("Producto actualizado (activo/inactivo).", "message")
    return redirect(url_for("admin.products_list"))


# =========================
# SUCURSALES (empresa actual)
# =========================
@admin_bp.get("/branches")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_list():
    company_id = _company_id()
    branches = (
        db.session.query(Branch)
        .filter(Branch.company_id == company_id)
        .order_by(Branch.is_warehouse.desc(), Branch.is_active.desc(), Branch.name.asc())
        .all()
    )
    return render_template("admin_branches.html", branches=branches)


@admin_bp.get("/branches/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_new_get():
    return render_template("admin_branch_new.html")


@admin_bp.post("/branches/new")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_new_post():
    company_id = _company_id()

    name = _clean_str(request.form.get("name"))
    is_warehouse = (_clean_str(request.form.get("is_warehouse")) == "1")

    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("admin.branches_new_get"))

    if db.session.query(Branch).filter_by(company_id=company_id, name=name).first():
        flash("Ya existe una sucursal con ese nombre en esta empresa.", "error")
        return redirect(url_for("admin.branches_new_get"))

    if is_warehouse:
        exists_wh = (
            db.session.query(Branch)
            .filter_by(company_id=company_id, is_warehouse=True, is_active=True)
            .first()
        )
        if exists_wh:
            flash("Ya existe una Bodega Central activa. No es recomendable crear otra.", "error")
            return redirect(url_for("admin.branches_new_get"))

    b = Branch(company_id=company_id, name=name, is_warehouse=is_warehouse, is_active=True)
    db.session.add(b)
    db.session.commit()

    flash("Sucursal creada.", "message")
    return redirect(url_for("admin.branches_list"))


@admin_bp.get("/branches/<int:branch_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_edit_get(branch_id: int):
    company_id = _company_id()
    branch = (
        db.session.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == company_id)
        .first()
    )
    if not branch:
        flash("Sucursal no encontrada.", "error")
        return redirect(url_for("admin.branches_list"))

    return render_template("admin_branch_edit.html", branch=branch)


@admin_bp.post("/branches/<int:branch_id>/edit")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_edit_post(branch_id: int):
    company_id = _company_id()
    branch = (
        db.session.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == company_id)
        .first()
    )
    if not branch:
        flash("Sucursal no encontrada.", "error")
        return redirect(url_for("admin.branches_list"))

    name = _clean_str(request.form.get("name"))
    is_warehouse = (_clean_str(request.form.get("is_warehouse")) == "1")

    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("admin.branches_edit_get", branch_id=branch_id))

    # nombre único por empresa
    exists = (
        db.session.query(Branch)
        .filter(
            Branch.company_id == company_id,
            Branch.name == name,
            Branch.id != branch.id
        )
        .first()
    )
    if exists:
        flash("Ya existe una sucursal con ese nombre.", "error")
        return redirect(url_for("admin.branches_edit_get", branch_id=branch_id))

    # si intenta marcar como bodega
    if is_warehouse and not branch.is_warehouse:
        exists_wh = (
            db.session.query(Branch)
            .filter_by(company_id=company_id, is_warehouse=True, is_active=True)
            .first()
        )
        if exists_wh:
            flash("Ya existe una Bodega Central activa. No es recomendable tener más de una.", "error")
            return redirect(url_for("admin.branches_edit_get", branch_id=branch_id))

    branch.name = name
    branch.is_warehouse = is_warehouse
    db.session.commit()

    flash("Sucursal actualizada.", "message")
    return redirect(url_for("admin.branches_list"))


@admin_bp.post("/branches/<int:branch_id>/toggle-active")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def branches_toggle_active(branch_id: int):
    """
    "Eliminar" seguro => desactivar.
    Seguridad extra: si es bodega y tiene stock, no dejar desactivar.
    """
    company_id = _company_id()

    branch = (
        db.session.query(Branch)
        .filter(Branch.id == branch_id, Branch.company_id == company_id)
        .first()
    )
    if not branch:
        flash("Sucursal no encontrada.", "error")
        return redirect(url_for("admin.branches_list"))

    # Si es bodega y tiene stock, no permitir desactivarla
    if branch.is_warehouse and branch.is_active:
        any_stock = (
            db.session.query(Inventory)
            .filter(
                Inventory.company_id == company_id,
                Inventory.location_type == LocationType.BRANCH,
                Inventory.location_id == branch.id,
                Inventory.qty > 0
            )
            .first()
        )
        if any_stock:
            flash("No puedes desactivar la Bodega porque tiene stock. Transfiere o ajusta primero.", "error")
            return redirect(url_for("admin.branches_list"))

    branch.is_active = not bool(branch.is_active)
    db.session.commit()

    flash("Sucursal actualizada (activa/inactiva).", "message")
    return redirect(url_for("admin.branches_list"))
