from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_required

from models import db
from models.client import Client, ClientType, IdentificationType
from models.membership import Role
from routes.guards import require_context, require_roles

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


def _company_id() -> int:
    return int(session["company_id"])


@clients_bp.get("/")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def list_clients():
    company_id = _company_id()
    q = (request.args.get("q") or "").strip()

    query = db.session.query(Client).filter(
        Client.company_id == company_id,
        Client.is_active == True,
    )

    if q:
        query = query.filter(Client.full_name.ilike(f"%{q}%"))

    clients = query.order_by(Client.full_name.asc()).limit(200).all()
    return render_template("clients_list.html", clients=clients, q=q)


@clients_bp.get("/new")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def new_get():
    return render_template("client_new.html", client_types=sorted(ClientType.ALL), id_types=sorted(IdentificationType.ALL))


@clients_bp.post("/new")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def new_post():
    company_id = _company_id()

    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    email = (request.form.get("email") or "").strip().lower() or None
    client_type = (request.form.get("client_type") or ClientType.NORMAL).upper()
    identification_type = (request.form.get("identification_type") or "").upper() or None
    identification_number = (request.form.get("identification_number") or "").strip() or None

    if not full_name:
        flash("Nombre del cliente es obligatorio.", "error")
        return redirect(url_for("clients.new_get"))

    if client_type not in ClientType.ALL:
        flash("Tipo de cliente inválido.", "error")
        return redirect(url_for("clients.new_get"))

    if identification_type and identification_type not in IdentificationType.ALL:
        flash("Tipo de identificación inválido.", "error")
        return redirect(url_for("clients.new_get"))

    # Validaciones simples por tipo (UX)
    if identification_type == IdentificationType.CEDULA and identification_number:
        if not (identification_number.isdigit() and len(identification_number) == 10):
            flash("Cédula inválida: debe tener 10 dígitos.", "error")
            return redirect(url_for("clients.new_get"))
    if identification_type == IdentificationType.RUC and identification_number:
        if not (identification_number.isdigit() and len(identification_number) == 13):
            flash("RUC inválido: debe tener 13 dígitos.", "error")
            return redirect(url_for("clients.new_get"))
    if identification_type == IdentificationType.PASAPORTE and identification_number:
        if len(identification_number) < 5:
            flash("Pasaporte inválido: demasiado corto.", "error")
            return redirect(url_for("clients.new_get"))


    c = Client(
        company_id=company_id,
        full_name=full_name,
        phone=phone,
        email=email,
        client_type=client_type,
        identification_type=identification_type,
        identification_number=identification_number,
        is_active=True,
    )
    db.session.add(c)
    db.session.commit()

    flash("Cliente creado.", "message")
    return redirect(url_for("clients.list_clients"))



@clients_bp.get("/<int:client_id>/edit")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def edit_get(client_id: int):
    company_id = _company_id()
    c = db.session.query(Client).filter(Client.company_id == company_id, Client.id == client_id, Client.is_active == True).first()
    if not c:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("clients.list_clients"))
    return render_template("client_edit.html", client=c, client_types=sorted(ClientType.ALL), id_types=sorted(IdentificationType.ALL))


@clients_bp.post("/<int:client_id>/edit")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def edit_post(client_id: int):
    company_id = _company_id()
    c = db.session.query(Client).filter(Client.company_id == company_id, Client.id == client_id, Client.is_active == True).first()
    if not c:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("clients.list_clients"))

    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip() or None
    email = (request.form.get("email") or "").strip().lower() or None
    client_type = (request.form.get("client_type") or ClientType.NORMAL).upper()
    identification_type = (request.form.get("identification_type") or "").upper() or None
    identification_number = (request.form.get("identification_number") or "").strip() or None

    if not full_name:
        flash("Nombre del cliente es obligatorio.", "error")
        return redirect(url_for("clients.edit_get", client_id=client_id))

    if client_type not in ClientType.ALL:
        flash("Tipo de cliente inválido.", "error")
        return redirect(url_for("clients.edit_get", client_id=client_id))

    if identification_type and identification_type not in IdentificationType.ALL:
        flash("Tipo de identificación inválido.", "error")
        return redirect(url_for("clients.edit_get", client_id=client_id))

    if identification_type == IdentificationType.CEDULA and identification_number:
        if not (identification_number.isdigit() and len(identification_number) == 10):
            flash("Cédula inválida: debe tener 10 dígitos.", "error")
            return redirect(url_for("clients.edit_get", client_id=client_id))
    if identification_type == IdentificationType.RUC and identification_number:
        if not (identification_number.isdigit() and len(identification_number) == 13):
            flash("RUC inválido: debe tener 13 dígitos.", "error")
            return redirect(url_for("clients.edit_get", client_id=client_id))
    if identification_type == IdentificationType.PASAPORTE and identification_number:
        if len(identification_number) < 5:
            flash("Pasaporte inválido: demasiado corto.", "error")
            return redirect(url_for("clients.edit_get", client_id=client_id))

    c.full_name = full_name
    c.phone = phone
    c.email = email
    c.client_type = client_type
    c.identification_type = identification_type
    c.identification_number = identification_number

    db.session.commit()
    flash("Cliente actualizado.", "message")
    return redirect(url_for("clients.list_clients"))


@clients_bp.post("/<int:client_id>/delete")
@login_required
@require_context()
@require_roles(Role.ADMIN, Role.OWNER)
def delete_post(client_id: int):
    company_id = _company_id()
    c = db.session.query(Client).filter(Client.company_id == company_id, Client.id == client_id, Client.is_active == True).first()
    if not c:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("clients.list_clients"))
    c.is_active = False
    db.session.commit()
    flash("Cliente eliminado.", "message")
    return redirect(url_for("clients.list_clients"))


@clients_bp.get("/search")
@login_required
@require_context()
@require_roles(Role.SELLER, Role.ADMIN, Role.OWNER)
def search():
    """
    Búsqueda rápida para el POS (JSON):
    /clients/search?q=...
    """
    company_id = _company_id()
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    clients = (
        db.session.query(Client)
        .filter(
            Client.company_id == company_id,
            Client.is_active == True,
            Client.full_name.ilike(f"%{q}%")
        )
        .order_by(Client.full_name.asc())
        .limit(10)
        .all()
    )

    return jsonify([
        {
            "id": c.id,
            "full_name": c.full_name,
            "client_type": c.client_type,
            "price_mode": c.price_mode,
            "phone": c.phone,
            "email": c.email
        }
        for c in clients
    ])
