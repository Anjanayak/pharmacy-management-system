from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles
from ..services import ai_service

router = APIRouter(prefix="/api/prescriptions", tags=["Prescriptions"])


@router.get("", response_model=List[schemas.PrescriptionOut])
def list_prescriptions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Prescription).order_by(models.Prescription.created_at.desc()).all()


@router.post("", response_model=schemas.PrescriptionOut, status_code=201)
def create_prescription(
    payload: schemas.PrescriptionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    """
    AI Prescription Assist step: takes raw prescription text (typed in, or in
    a real deployment the output of an OCR pass over an uploaded image),
    extracts medicine name / dosage / frequency per line, matches against the
    catalog, and flags a possible drug-interaction warning across the whole
    prescription for pharmacist review.
    """
    prescription = models.Prescription(
        customer_id=payload.customer_id,
        uploaded_by=current_user.id,
        raw_text=payload.raw_text,
    )
    db.add(prescription)
    db.flush()

    catalog = db.query(models.Medicine).filter(models.Medicine.is_active == True).all()  # noqa: E712
    extracted_items = ai_service.parse_prescription_text(payload.raw_text, catalog)

    interaction_hits = ai_service.check_drug_interactions([item["extracted_name"] for item in extracted_items])
    interaction_summary = "; ".join(f"{h['medicines']}: {h['message']}" for h in interaction_hits) or None

    for item in extracted_items:
        warning = item["warning_flag"]
        if interaction_summary:
            warning = f"{warning + ' | ' if warning else ''}Interaction risk: {interaction_summary}"
        db.add(models.PrescriptionItem(
            prescription_id=prescription.id,
            extracted_name=item["extracted_name"],
            matched_medicine_id=item["matched_medicine_id"],
            dosage=item["dosage"],
            frequency=item["frequency"],
            warning_flag=warning,
        ))

    db.commit()
    db.refresh(prescription)
    return prescription


@router.get("/{prescription_id}", response_model=schemas.PrescriptionOut)
def get_prescription(prescription_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    p = db.query(models.Prescription).get(prescription_id)
    if not p:
        raise HTTPException(404, "Prescription not found")
    return p


@router.patch("/{prescription_id}/review", response_model=schemas.PrescriptionOut)
def review_prescription(
    prescription_id: int,
    payload: schemas.PrescriptionReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    p = db.query(models.Prescription).get(prescription_id)
    if not p:
        raise HTTPException(404, "Prescription not found")
    p.status = payload.status
    db.commit()
    db.refresh(p)
    return p
