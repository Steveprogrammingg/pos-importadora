import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")

    # Offline-first: SQLite local
    DB_PATH = os.environ.get("DB_PATH", os.path.join(basedir, "pos.db"))
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cookies de sesión más seguras (ajusta en producción)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
