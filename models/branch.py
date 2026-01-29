from datetime import datetime
from . import db

class Branch(db.Model):
    __tablename__ = "branches"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    is_warehouse = db.Column(db.Boolean, default=False, nullable=False)  # Bodega Central = True
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    company = db.relationship("Company", back_populates="branches")

    __table_args__ = (
        db.UniqueConstraint("company_id", "name", name="uq_branch_company_name"),
    )

    def __repr__(self) -> str:
        return f"<Branch {self.id} {self.name} company={self.company_id} warehouse={self.is_warehouse}>"
