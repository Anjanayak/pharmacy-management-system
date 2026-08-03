from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles
from ..config import settings

router = APIRouter(prefix="/api/medicines", tags=["Medicines"])


def _with_stock(db: Session, medicine: models.Medicine) -> schemas.MedicineOut:
    total = db.query(func.coalesce(func.sum(models.Batch.quantity), 0)).filter(
        models.Batch.medicine_id == medicine.id
    ).scalar()
    out = schemas.MedicineOut.model_validate(medicine)
    out.total_stock = int(total)
    return out


@router.get("", response_model=List[schemas.MedicineOut])
def list_medicines(
    search: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Medicine).filter(models.Medicine.is_active == True)  # noqa: E712
    if search:
        like = f"%{search}%"
        query = query.filter(
            (models.Medicine.name.ilike(like)) | (models.Medicine.generic_name.ilike(like))
        )
    if category:
        query = query.filter(models.Medicine.category == category)
    limit = max(1, min(limit, 200))
    medicines = query.order_by(models.Medicine.name).offset(max(0, skip)).limit(limit).all()
    return [_with_stock(db, m) for m in medicines]


@router.post("", response_model=schemas.MedicineOut, status_code=201)
def create_medicine(
    payload: schemas.MedicineCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    medicine = models.Medicine(**payload.model_dump())
    db.add(medicine)
    db.commit()
    db.refresh(medicine)
    return _with_stock(db, medicine)


@router.get("/{medicine_id}", response_model=schemas.MedicineOut)
def get_medicine(medicine_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    medicine = db.query(models.Medicine).get(medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")
    return _with_stock(db, medicine)


@router.put("/{medicine_id}", response_model=schemas.MedicineOut)
def update_medicine(
    medicine_id: int,
    payload: schemas.MedicineCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    medicine = db.query(models.Medicine).get(medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")
    for key, value in payload.model_dump().items():
        setattr(medicine, key, value)
    db.commit()
    db.refresh(medicine)
    return _with_stock(db, medicine)


@router.delete("/{medicine_id}", status_code=204)
def deactivate_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin)),
):
    medicine = db.query(models.Medicine).get(medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")
    medicine.is_active = False
    db.commit()
    return None


# ---------- Batches ----------
@router.get("/{medicine_id}/batches", response_model=List[schemas.BatchOut])
def list_batches(medicine_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Batch).filter(models.Batch.medicine_id == medicine_id).order_by(models.Batch.expiry_date).all()


@router.post("/batches", response_model=schemas.BatchOut, status_code=201)
def add_batch(
    payload: schemas.BatchCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    medicine = db.query(models.Medicine).get(payload.medicine_id)
    if not medicine:
        raise HTTPException(404, "Medicine not found")

    batch = models.Batch(**payload.model_dump())
    db.add(batch)
    db.flush()

    movement = models.StockMovement(
        medicine_id=payload.medicine_id,
        batch_id=batch.id,
        movement_type=models.MovementType.stock_in,
        quantity=payload.quantity,
        reference_type="batch_received",
        reference_id=batch.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/alerts/expiring", response_model=List[schemas.BatchOut])
def expiring_batches(
    days: int = settings.EXPIRY_WARNING_DAYS,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cutoff = date.today() + timedelta(days=days)
    return (
        db.query(models.Batch)
        .filter(models.Batch.expiry_date <= cutoff, models.Batch.quantity > 0)
        .order_by(models.Batch.expiry_date)
        .all()
    )


@router.get("/alerts/low-stock")
def low_stock_medicines(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    medicines = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    low = []
    for m in medicines:
        total = db.query(func.coalesce(func.sum(models.Batch.quantity), 0)).filter(
            models.Batch.medicine_id == m.id
        ).scalar()
        if total <= m.reorder_level:
            low.append({"medicine_id": m.id, "name": m.name, "current_stock": int(total), "reorder_level": m.reorder_level})
    return low
