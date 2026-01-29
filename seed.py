from app import create_app
from models import db
from models.user import User
from models.company import Company
from models.branch import Branch
from models.membership import CompanyUser, Role

# NUEVO: rol global Owner/SuperAdmin
from models.system_role import SystemUserRole, SystemRole


def run():
    app = create_app()
    with app.app_context():
        # ✅ Importante:
        # No usamos db.create_all() porque ya estamos trabajando con migraciones (Flask-Migrate).
        # Asegúrate de haber corrido: flask db upgrade

        # 1) Empresa demo
        company = db.session.query(Company).filter_by(name="Panadería X").first()
        if not company:
            company = Company(name="Panadería X", is_active=True)
            db.session.add(company)
            db.session.flush()

        # 2) Bodega central + sucursal matriz
        bodega = db.session.query(Branch).filter_by(company_id=company.id, name="Bodega Central").first()
        if not bodega:
            bodega = Branch(company_id=company.id, name="Bodega Central", is_warehouse=True, is_active=True)
            db.session.add(bodega)

        suc1 = db.session.query(Branch).filter_by(company_id=company.id, name="Sucursal Matriz").first()
        if not suc1:
            suc1 = Branch(company_id=company.id, name="Sucursal Matriz", is_warehouse=False, is_active=True)
            db.session.add(suc1)

        # 3) Usuario admin demo
        user = db.session.query(User).filter_by(email="admin@demo.com").first()
        if not user:
            user = User(email="admin@demo.com", full_name="Admin Demo", is_active=True)
            user.set_password("admin1234")
            db.session.add(user)
            db.session.flush()
        else:
            # Opcional: asegura que esté activo
            user.is_active = True

        # 4) Rol global OWNER (para crear empresas)
        owner = db.session.query(SystemUserRole).filter_by(user_id=user.id).first()
        if not owner:
            db.session.add(SystemUserRole(user_id=user.id, role=SystemRole.OWNER))

        # 5) Membership ADMIN (acceso global a la empresa: branch_id = NULL)
        m = (
            db.session.query(CompanyUser)
            .filter_by(user_id=user.id, company_id=company.id, branch_id=None)
            .first()
        )
        if not m:
            m = CompanyUser(
                user_id=user.id,
                company_id=company.id,
                branch_id=None,
                role=Role.ADMIN,
                is_active=True
            )
            db.session.add(m)
        else:
            m.is_active = True
            m.role = Role.ADMIN

        db.session.commit()

        print("✅ Seed listo.")
        print("Login: admin@demo.com / admin1234")
        print("Rol global: OWNER (puede crear empresas)")
        print("Permiso en empresa: ADMIN (puede gestionar sucursales/usuarios/productos)")


if __name__ == "__main__":
    run()
