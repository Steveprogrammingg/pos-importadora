from datetime import datetime
from . import db
from flask_login import login_required, current_user


class Role:
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SELLER = "SELLER"

    ALL = {OWNER, ADMIN, SELLER}

class CompanyUser(db.Model):
    __tablename__ = "company_users"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    # Si es vendedor: branch_id obligatorio (recomendado).
    # Si es admin: branch_id puede ser NULL (acceso global en esa empresa).
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)

    role = db.Column(db.String(20), nullable=False)  # OWNER / ADMIN / SELLER
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="memberships")
    company = db.relationship("Company", back_populates="users")
    branch = db.relationship("Branch")

    __table_args__ = (
        db.UniqueConstraint("user_id", "company_id", "branch_id", name="uq_user_company_branch"),
    )

    def __repr__(self) -> str:
        return f"<CompanyUser user={self.user_id} company={self.company_id} branch={self.branch_id} role={self.role}>"
