from __future__ import annotations

from flask import Blueprint, jsonify, session
from flask_login import login_required

from models import db
from models.sync_event import SyncEvent, SyncEventStatus
from routes.guards import require_context


sync_bp = Blueprint("sync", __name__, url_prefix="/sync")


@sync_bp.get("/status")
@login_required
@require_context()
def status():
    company_id = int(session["company_id"])
    branch_id = int(session["branch_id"])

    counts = {
        s: db.session.query(SyncEvent.id)
        .filter(
            SyncEvent.company_id == company_id,
            SyncEvent.branch_id == branch_id,
            SyncEvent.status == s,
        )
        .count()
        for s in (
            SyncEventStatus.PENDING,
            SyncEventStatus.SENT,
            SyncEventStatus.APPLIED,
            SyncEventStatus.ERROR,
        )
    }
    return jsonify({"company_id": company_id, "branch_id": branch_id, "counts": counts})


@sync_bp.post("/enqueue")
@login_required
@require_context()
def enqueue_demo():
    """Endpoint demo para pruebas de sincronización.

    Más adelante: cada venta/gasto/inventario va a crear eventos automáticamente.
    """
    company_id = int(session["company_id"])
    branch_id = int(session["branch_id"])
    e = SyncEvent(company_id=company_id, branch_id=branch_id, entity="DEMO", entity_id=None, action="PING")
    db.session.add(e)
    db.session.commit()
    return jsonify({"ok": True, "id": e.id})
