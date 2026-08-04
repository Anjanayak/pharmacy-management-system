from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user
from ..services import ai_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.post("/check-interactions")
def check_interactions(payload: schemas.InteractionCheckRequest, current_user: models.User = Depends(get_current_user)):
    hits = ai_service.check_drug_interactions(payload.medicine_names)
    return {"checked": payload.medicine_names, "interactions_found": hits}


@router.post("/substitutes")
def substitutes(
    payload: schemas.SubstituteRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    medicine = db.get(models.Medicine, payload.medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")
    all_medicines = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    subs = ai_service.suggest_substitutes(medicine, all_medicines)
    return {"medicine": medicine.name, "substitutes": [{"id": s.id, "name": s.name, "generic_name": s.generic_name} for s in subs]}


@router.get("/forecast/{medicine_id}")
def demand_forecast(
    medicine_id: int,
    lookback_days: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    medicine = db.get(models.Medicine, medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")
    return ai_service.forecast_demand(db, medicine_id, lookback_days)


@router.get("/expiry-risk/{batch_id}")
def expiry_risk(batch_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    batch = db.get(models.Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found")
    return ai_service.predict_expiry_risk(batch)