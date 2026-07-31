from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles
from ..services import ai_service
from ..config import settings

router = APIRouter(prefix="/api/stock", tags=["Stock"])
alerts_router = APIRouter(prefix="/api/alerts", tags=["Alerts"])
reports_router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/movements", response_model=List[schemas.StockMovementOut])
def list_movements(
    medicine_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.StockMovement)
    if medicine_id:
        query = query.filter(models.StockMovement.medicine_id == medicine_id)
    return query.order_by(models.StockMovement.created_at.desc()).limit(500).all()


@router.post("/adjust", response_model=schemas.StockMovementOut, status_code=201)
def adjust_stock(
    payload: schemas.StockAdjustment,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    """Manual correction (damage, audit mismatch, etc). Positive quantity
    adds stock back, negative removes it."""
    batch = db.query(models.Batch).get(payload.batch_id)
    if not batch or batch.medicine_id != payload.medicine_id:
        raise HTTPException(404, "Batch not found for this medicine")

    new_qty = batch.quantity + payload.quantity
    if new_qty < 0:
        raise HTTPException(400, "Adjustment would result in negative stock")
    batch.quantity = new_qty

    movement_type = models.MovementType.damage if payload.quantity < 0 else models.MovementType.adjustment
    movement = models.StockMovement(
        medicine_id=payload.medicine_id,
        batch_id=payload.batch_id,
        movement_type=movement_type,
        quantity=abs(payload.quantity),
        reference_type="manual_adjustment",
        reference_id=None,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


# ---------- Alerts (expiry / low stock / interaction) ----------
@alerts_router.get("", response_model=List[schemas.AlertOut])
def list_alerts(
    resolved: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return db.query(models.Alert).filter(models.Alert.resolved == resolved).order_by(models.Alert.created_at.desc()).all()


@alerts_router.post("/scan", response_model=List[schemas.AlertOut])
def scan_and_generate_alerts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    """Runs the expiry + low-stock rule engine and inserts fresh Alert rows
    for anything not already flagged and unresolved. Call this on a schedule
    (e.g. a daily cron / background worker) in a real deployment."""
    created = []

    # Expiry risk
    batches = db.query(models.Batch).filter(models.Batch.quantity > 0).all()
    for batch in batches:
        risk = ai_service.predict_expiry_risk(batch)
        if risk["risk_level"] in ("critical", "high", "expired"):
            exists = db.query(models.Alert).filter(
                models.Alert.batch_id == batch.id,
                models.Alert.type == models.AlertType.expiry,
                models.Alert.resolved == False,  # noqa: E712
            ).first()
            if not exists:
                alert = models.Alert(
                    type=models.AlertType.expiry,
                    medicine_id=batch.medicine_id,
                    batch_id=batch.id,
                    message=f"Batch {batch.batch_number} risk level: {risk['risk_level']} "
                            f"({risk['days_left']} days left, qty {risk['quantity']})",
                    severity="high" if risk["risk_level"] in ("critical", "expired") else "medium",
                )
                db.add(alert)
                created.append(alert)

    # Low stock
    medicines = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    for m in medicines:
        total = db.query(func.coalesce(func.sum(models.Batch.quantity), 0)).filter(
            models.Batch.medicine_id == m.id
        ).scalar()
        if total <= m.reorder_level:
            exists = db.query(models.Alert).filter(
                models.Alert.medicine_id == m.id,
                models.Alert.type == models.AlertType.low_stock,
                models.Alert.resolved == False,  # noqa: E712
            ).first()
            if not exists:
                alert = models.Alert(
                    type=models.AlertType.low_stock,
                    medicine_id=m.id,
                    message=f"{m.name} stock ({int(total)}) at/below reorder level ({m.reorder_level})",
                    severity="medium",
                )
                db.add(alert)
                created.append(alert)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


@alerts_router.patch("/{alert_id}/resolve", response_model=schemas.AlertOut)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    alert = db.query(models.Alert).get(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.resolved = True
    db.commit()
    db.refresh(alert)
    return alert


# ---------- Reports ----------
@reports_router.get("/fast-moving")
def fast_moving_medicines(days: int = 30, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(models.StockMovement.medicine_id, func.sum(models.StockMovement.quantity).label("total_sold"))
        .filter(models.StockMovement.movement_type == models.MovementType.stock_out, models.StockMovement.created_at >= since)
        .group_by(models.StockMovement.medicine_id)
        .order_by(func.sum(models.StockMovement.quantity).desc())
        .limit(20)
        .all()
    )
    result = []
    for medicine_id, total_sold in rows:
        med = db.query(models.Medicine).get(medicine_id)
        result.append({"medicine_id": medicine_id, "name": med.name if med else "Unknown", "total_sold": int(total_sold)})
    return result


@reports_router.get("/dead-stock")
def dead_stock(days: int = 60, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    since = date.today() - timedelta(days=days)
    sold_recently_ids = {
        row[0] for row in db.query(models.StockMovement.medicine_id).filter(
            models.StockMovement.movement_type == models.MovementType.stock_out,
            models.StockMovement.created_at >= since,
        ).distinct()
    }
    medicines = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    dead = []
    for m in medicines:
        if m.id not in sold_recently_ids:
            total = db.query(func.coalesce(func.sum(models.Batch.quantity), 0)).filter(
                models.Batch.medicine_id == m.id
            ).scalar()
            if total and total > 0:
                dead.append({"medicine_id": m.id, "name": m.name, "current_stock": int(total)})
    return dead


@reports_router.get("/expiry-loss")
def expiry_loss(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    expired_batches = db.query(models.Batch).filter(models.Batch.expiry_date < date.today(), models.Batch.quantity > 0).all()
    total_loss = 0.0
    details = []
    for b in expired_batches:
        loss = b.quantity * b.cost_price
        total_loss += loss
        details.append({
            "batch_id": b.id, "medicine_id": b.medicine_id, "batch_number": b.batch_number,
            "quantity": b.quantity, "expiry_date": str(b.expiry_date), "estimated_loss": round(loss, 2),
        })
    return {"total_estimated_loss": round(total_loss, 2), "batches": details}


@reports_router.get("/daily-sales")
def daily_sales(target_date: date = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    target_date = target_date or date.today()
    invoices = db.query(models.Invoice).filter(func.date(models.Invoice.created_at) == target_date).all()
    total = sum(inv.total_amount for inv in invoices)
    return {"date": str(target_date), "invoice_count": len(invoices), "total_sales": round(total, 2)}


@reports_router.get("/reorder-needs")
def reorder_needs(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    medicines = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    needs = []
    for m in medicines:
        total = db.query(func.coalesce(func.sum(models.Batch.quantity), 0)).filter(
            models.Batch.medicine_id == m.id
        ).scalar()
        if total <= m.reorder_level:
            forecast = ai_service.forecast_demand(db, m.id)
            needs.append({
                "medicine_id": m.id, "name": m.name, "current_stock": int(total),
                "reorder_level": m.reorder_level, "projected_demand_next_30_days": forecast["projected_demand_next_30_days"],
            })
    return needs
