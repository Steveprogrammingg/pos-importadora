from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from models import db
from models.company import Company
from routes.guards import require_system_owner

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")


def _clean_str(v: str | None) -> str:
    return (v or "").strip()


@owner_bp.get("/companies")
@login_required
@require_system_owner()
def companies_list():
    companies = (
        db.session.query(Company)
        .order_by(Company.is_active.desc(), Company.name.asc())
        .all()
    )
    return render_template("owner_companies.html", companies=companies)


@owner_bp.get("/companies/new")
@login_required
@require_system_owner()
def companies_new_get():
    return render_template("owner_company_new.html")


@owner_bp.post("/companies/new")
@login_required
@require_system_owner()
def companies_new_post():
    name = _clean_str(request.form.get("name"))
    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("owner.companies_new_get"))

    exists = db.session.query(Company).filter(Company.name == name).first()
    if exists:
        flash("Ya existe una empresa con ese nombre.", "error")
        return redirect(url_for("owner.companies_new_get"))

    c = Company(name=name, is_active=True)
    db.session.add(c)
    db.session.commit()

    flash("Empresa creada.", "message")
    return redirect(url_for("owner.companies_list"))


@owner_bp.get("/companies/<int:company_id>/edit")
@login_required
@require_system_owner()
def companies_edit_get(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        flash("Empresa no encontrada.", "error")
        return redirect(url_for("owner.companies_list"))
    return render_template("owner_company_edit.html", company=company)


@owner_bp.post("/companies/<int:company_id>/edit")
@login_required
@require_system_owner()
def companies_edit_post(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        flash("Empresa no encontrada.", "error")
        return redirect(url_for("owner.companies_list"))

    name = _clean_str(request.form.get("name"))
    if not name:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("owner.companies_edit_get", company_id=company_id))

    exists = (
        db.session.query(Company)
        .filter(Company.name == name, Company.id != company.id)
        .first()
    )
    if exists:
        flash("Ya existe otra empresa con ese nombre.", "error")
        return redirect(url_for("owner.companies_edit_get", company_id=company_id))

    company.name = name
    db.session.commit()

    flash("Empresa actualizada.", "message")
    return redirect(url_for("owner.companies_list"))


@owner_bp.post("/companies/<int:company_id>/toggle-active")
@login_required
@require_system_owner()
def companies_toggle_active(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        flash("Empresa no encontrada.", "error")
        return redirect(url_for("owner.companies_list"))

    company.is_active = not bool(company.is_active)
    db.session.commit()

    flash("Empresa actualizada (activa/inactiva).", "message")
    return redirect(url_for("owner.companies_list"))
