from flask import Flask
from flask_migrate import Migrate

from config import Config
from models import db, login_manager


migrate = Migrate()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # -------------------------
    # Extensiones
    # -------------------------
    db.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login_get"

    # -------------------------
    # Importar modelos (Alembic)
    # -------------------------
    from models.company import Company  # noqa: F401
    from models.branch import Branch  # noqa: F401
    from models.user import User  # noqa: F401
    from models.membership import CompanyUser  # noqa: F401
    from models.product import Product  # noqa: F401
    from models.client import Client  # noqa: F401
    from models.system_role import SystemUserRole  # noqa: F401

    from models.inventory import Inventory  # noqa: F401
    from models.kardex import KardexMovement  # noqa: F401
    from models.sale import Sale, SaleItem  # noqa: F401

    # Offline-first sync
    from models.sync_event import SyncEvent  # noqa: F401

    # Finanzas
    from models.expense import Expense  # noqa: F401
    from models.cash_movement import CashMovement  # noqa: F401

    # -------------------------
    # Blueprints
    # -------------------------
    from routes.auth import auth_bp
    from routes.context import context_bp
    from routes.main import main_bp

    from routes.admin import admin_bp
    from routes.owner import owner_bp

    from routes.pos import pos_bp
    from routes.clients import clients_bp

    from routes.inventory import inventory_bp
    from routes.inventory_admin import inventory_admin_bp
    from routes.kardex import kardex_bp

    from routes.reports import reports_bp
    from routes.reports_top import reports_top_bp

    from routes.finance import finance_bp
    from routes.sync import sync_bp

    # Registrar blueprints (limpio y escalable)
    blueprints = [
        auth_bp,
        context_bp,
        main_bp,

        # Admin / Owner
        admin_bp,
        owner_bp,

        # Operación
        pos_bp,
        clients_bp,
        inventory_bp,
        inventory_admin_bp,
        kardex_bp,

        # Reportes
        reports_bp,
        reports_top_bp,

        # Finanzas
        finance_bp,

        # Sync
        sync_bp,
    ]

    for bp in blueprints:
        app.register_blueprint(bp)

    # -------------------------
    # Logging + manejo global de errores
    # -------------------------
    import os
    import logging
    from logging.handlers import RotatingFileHandler
    from flask import render_template, flash, request

    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)

    @app.errorhandler(500)
    def _handle_500(e):
        app.logger.exception("Error 500 no manejado: %s %s", request.method, request.path)
        flash("Ocurrió un error interno. El problema fue registrado.", "error")
        return render_template("error.html", message=None), 500

    @app.errorhandler(403)
    def _handle_403(e):
        flash("No tienes permisos para acceder.", "error")
        return render_template("error.html", message="Acceso denegado."), 403

    @app.errorhandler(404)
    def _handle_404(e):
        return render_template("404.html"), 404

    return app


app = create_app()


if __name__ == "__main__":
    # Debug controlado por config / variables de entorno
    app.run(debug=app.config.get("DEBUG", False))
