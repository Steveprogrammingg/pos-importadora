from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from models import db
from models.branch import Branch
from models.membership import CompanyUser, Role
from models.system_role import SystemUserRole
from routes import context_bp


def _available_memberships():
    """Trae TODAS las membresías activas del usuario cargando company y branch."""
    return (
        db.session.query(CompanyUser)
        .options(joinedload(CompanyUser.company), joinedload(CompanyUser.branch))
        .filter(CompanyUser.user_id == current_user.id, CompanyUser.is_active.is_(True))
        .all()
    )


def _set_context(company_id: int, branch_id: int, role: str | None = None):
    session["company_id"] = int(company_id)
    session["branch_id"] = int(branch_id)
    if role:
        session["role"] = role


def _clear_context():
    session.pop("company_id", None)
    session.pop("branch_id", None)
    session.pop("role", None)


def _set_system_role():
    r = db.session.query(SystemUserRole).filter(SystemUserRole.user_id == current_user.id).first()
    session["system_role"] = r.role if r else None


@context_bp.get("/select-context")
@login_required
def select_context():
    memberships = _available_memberships()
    _set_system_role()

    if not memberships:
        flash("Tu usuario no tiene acceso a ninguna empresa. Contacta al administrador.", "error")
        return render_template("select_context.html", companies=[])

    # Caso vendedor con 1 sola sucursal: entra directo
    if (
        len(memberships) == 1
        and memberships[0].role == Role.SELLER
        and memberships[0].branch_id is not None
    ):
        m = memberships[0]
        _set_context(m.company_id, m.branch_id, role=m.role)
        return redirect(url_for("main.dashboard"))

    # Agrupar para mostrar selector
    companies = {}
    for m in memberships:
        companies.setdefault(m.company_id, {"company": m.company, "memberships": []})
        companies[m.company_id]["memberships"].append(m)

    return render_template("select_context.html", companies=list(companies.values()))


@context_bp.post("/select-context")
@login_required
def select_context_post():
    company_id = request.form.get("company_id", type=int)
    branch_id = request.form.get("branch_id", type=int)

    if not company_id:
        flash("Selecciona una empresa.", "error")
        return redirect(url_for("context.select_context"))

    if not branch_id:
        flash("Selecciona una sucursal para continuar.", "error")
        return redirect(url_for("context.select_context"))

    memberships = _available_memberships()
    _set_system_role()

    # 1) Validar que la sucursal pertenece a la empresa y está activa
    branch_ok = (
        db.session.query(Branch.id)
        .filter(
            Branch.id == branch_id,
            Branch.company_id == company_id,
            Branch.is_active.is_(True),
        )
        .first()
        is not None
    )
    if not branch_ok:
        flash("Sucursal inválida o inactiva para esa empresa.", "error")
        return redirect(url_for("context.select_context"))

    # 2) Validar permiso
    allowed = False
    role = None
    for m in memberships:
        if m.company_id != company_id:
            continue

        # membership global (branch NULL) => puede elegir cualquier sucursal activa de esa empresa
        if m.branch_id is None:
            allowed = True
            role = m.role
            break

        # membership amarrada
        if m.branch_id == branch_id:
            allowed = True
            role = m.role
            break

        # ADMIN/OWNER en empresa => acceso global (evita bloqueos)
        if m.role in (Role.ADMIN, Role.OWNER):
            allowed = True
            role = m.role
            break

    if not allowed:
        flash("No tienes permiso para ese contexto.", "error")
        return redirect(url_for("context.select_context"))

    _set_context(company_id, branch_id, role=role)
    return redirect(url_for("main.dashboard"))


@context_bp.post("/clear-context")
@login_required
def clear_context():
    _clear_context()
    flash("Contexto limpiado. Selecciona empresa y sucursal.", "info")
    return redirect(url_for("context.select_context"))
