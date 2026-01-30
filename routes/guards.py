from functools import wraps

from flask import flash, redirect, session, url_for
from flask_login import current_user

from models import db
from models.branch import Branch
from models.membership import CompanyUser, Role
from models.system_role import SystemRole, SystemUserRole


def get_context_ids():
    company_id = session.get("company_id")
    branch_id = session.get("branch_id")
    if company_id is None or branch_id is None:
        return None, None
    try:
        return int(company_id), int(branch_id)
    except (TypeError, ValueError):
        return None, None


def _branch_belongs_and_active(company_id: int, branch_id: int) -> bool:
    return (
        db.session.query(Branch.id)
        .filter(
            Branch.id == branch_id,
            Branch.company_id == company_id,
            Branch.is_active.is_(True),
        )
        .first()
        is not None
    )


def _get_membership_for_context(user_id: int, company_id: int, branch_id: int):
    """Regla corregida:

    - Si el usuario es ADMIN u OWNER en la empresa, puede entrar a cualquier sucursal,
      incluso si su membership tiene branch_id.
    - Si es SELLER, debe coincidir con la sucursal seleccionada.
    - Si existe una membership global (branch_id NULL), también sirve.
    """

    memberships = (
        db.session.query(CompanyUser)
        .filter(
            CompanyUser.user_id == user_id,
            CompanyUser.company_id == company_id,
            CompanyUser.is_active.is_(True),
        )
        .all()
    )

    # 1) ADMIN/OWNER => acceso global a cualquier branch (evita bloqueos)
    for m in memberships:
        if m.role in (Role.ADMIN, Role.OWNER):
            return m

    # 2) SELLER => debe coincidir la sucursal
    for m in memberships:
        if m.branch_id == branch_id:
            return m

    # 3) Global legacy: branch_id NULL
    for m in memberships:
        if m.branch_id is None:
            return m

    return None


def require_context():
    """Obliga a que exista company_id y branch_id en sesión."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            company_id, branch_id = get_context_ids()
            if not company_id or not branch_id:
                flash("Selecciona Empresa y Sucursal para continuar.", "error")
                return redirect(url_for("context.select_context"))

            # Validación extra: branch debe existir y pertenecer a la empresa
            if not _branch_belongs_and_active(company_id, branch_id):
                flash("Sucursal inválida o inactiva. Selecciona contexto nuevamente.", "error")
                session.pop("company_id", None)
                session.pop("branch_id", None)
                return redirect(url_for("context.select_context"))

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_roles(*allowed_roles):
    """Valida:

    - Contexto seleccionado (company_id, branch_id)
    - La sucursal pertenece a la empresa y está activa
    - Usuario tiene membership activo para esa empresa
      - Si está amarrado a branch: debe coincidir
      - Si es global: válido para cualquier branch de esa empresa
    - Rol permitido
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            company_id, branch_id = get_context_ids()
            if not company_id or not branch_id:
                flash("Selecciona Empresa y Sucursal para continuar.", "error")
                return redirect(url_for("context.select_context"))

            if not _branch_belongs_and_active(company_id, branch_id):
                flash("Sucursal inválida o inactiva. Selecciona contexto nuevamente.", "error")
                session.pop("company_id", None)
                session.pop("branch_id", None)
                return redirect(url_for("context.select_context"))

            membership = _get_membership_for_context(current_user.id, company_id, branch_id)
            if not membership:
                flash("No tienes acceso a esta empresa o sucursal.", "error")
                return redirect(url_for("context.select_context"))

            if membership.role not in allowed_roles:
                flash("No tienes permisos para acceder a esta sección.", "error")
                return redirect(url_for("pos.sale"))

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_system_owner():
    """Permite acceso a /owner/* basado en rol GLOBAL del sistema (system_user_roles)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            r = (
                db.session.query(SystemUserRole)
                .filter(SystemUserRole.user_id == current_user.id)
                .first()
            )
            if not r or r.role != SystemRole.OWNER:
                flash("No tienes permisos para acceder a esta sección.", "error")
                return redirect(url_for("pos.sale"))
            return fn(*args, **kwargs)

        return wrapper

    return decorator
