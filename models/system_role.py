from datetime import datetime
from . import db

class SystemRole:
    OWNER = "OWNER"
    ALL = {OWNER}

class SystemUserRole(db.Model):
    """
    Rol global del sistema (fuera de empresas).
    - Si un user es OWNER aquí, puede crear empresas.
    """
    __tablename__ = "system_user_roles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    role = db.Column(db.String(20), nullable=False)  # OWNER
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SystemUserRole user={self.user_id} role={self.role}>"
