import io
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles
from ..services import ai_service, llm_service

router = APIRouter(prefix="/api/prescriptions", tags=["Prescriptions"])

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB


@router.post("/extract-text")
async def extract_text_from_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    """
    OCR step of AI Prescription Assist: runs Tesseract OCR (offline, no
    external API) over an uploaded prescription image and returns the raw
    extracted text for the pharmacist to review/edit before it is submitted
    to POST /api/prescriptions, which then performs medicine/dosage/frequency
    parsing and drug-interaction checking on that text.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Unsupported image type '{file.content_type}'. Use PNG, JPEG, or WEBP.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Image too large (max 8 MB).")

    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(contents))
        extracted_text = pytesseract.image_to_string(image).strip()
    except ImportError:
        raise HTTPException(500, "OCR dependencies not installed on the server.")
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(500, "Tesseract OCR engine not found on the server. Rebuild the backend image.")
    except Exception as exc:
        raise HTTPException(400, f"Could not read image: {exc}")

    if not extracted_text:
        extracted_text = ""

    return {"extracted_text": extracted_text, "filename": file.filename}


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

    if llm_service.is_configured():
        try:
            llm_items = llm_service.parse_prescription_text_llm(payload.raw_text)
            # Re-run catalog matching locally (same logic as the rule-based
            # path) so behavior is consistent regardless of extraction source.
            extracted_items = []
            for item in llm_items:
                name = item.get("extracted_name", "")
                matched = None
                norm = name.strip().lower()
                for med in catalog:
                    candidates = [med.name.lower()] + ([med.generic_name.lower()] if med.generic_name else [])
                    if any(c and (c in norm or norm in c) for c in candidates):
                        matched = med
                        break
                extracted_items.append({
                    "extracted_name": name,
                    "matched_medicine_id": matched.id if matched else None,
                    "dosage": item.get("dosage"),
                    "frequency": item.get("frequency"),
                    "warning_flag": None if matched else "No exact catalog match - please verify manually",
                })

            llm_hits = llm_service.check_drug_interactions_llm(
                [item["extracted_name"] for item in extracted_items]
            )
            interaction_hits = [
                {"medicines": h.get("medicines", []), "message": h.get("message", "")}
                for h in llm_hits
            ]
        except llm_service.LLMServiceError:
            # Network hiccup, expired key, rate limit, etc. — fall back to the
            # offline rule-based layer rather than failing the whole request.
            extracted_items = ai_service.parse_prescription_text(payload.raw_text, catalog)
            interaction_hits = ai_service.check_drug_interactions(
                [item["extracted_name"] for item in extracted_items]
            )
    else:
        extracted_items = ai_service.parse_prescription_text(payload.raw_text, catalog)
        interaction_hits = ai_service.check_drug_interactions(
            [item["extracted_name"] for item in extracted_items]
        )

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
    p = db.get(models.Prescription, prescription_id)
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
    p = db.get(models.Prescription, prescription_id)
    if not p:
        raise HTTPException(404, "Prescription not found")
    p.status = payload.status
    db.commit()
    db.refresh(p)
    return p
