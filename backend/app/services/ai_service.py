"""
AI / rules layer for the pharmacy system.

This module intentionally works fully offline with no external API key so the
project runs out of the box. Every function below is written as a clean seam:
swap the body of any function for a real call to OpenAI/Anthropic/a local LLM
(e.g. via LangChain) later without touching the routers that call it.

Covers, per the project brief:
- Prescription text parsing (stand-in for OCR + NER extraction)
- Drug interaction alerting (static interaction-rule table)
- Substitute medicine suggestion (category / generic-name matching)
- Expiry risk prediction (days-to-expiry vs quantity heuristic)
- Simple demand forecasting (moving average over stock-out movements)
"""

import re
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from ..models import Medicine, Batch, StockMovement, MovementType
from ..config import settings

# --------------------------------------------------------------------------
# Static knowledge bases (would live in a real drug-reference DB / vector
# store in production; kept in-code here so the project needs zero setup)
# --------------------------------------------------------------------------

# Pairs (order-independent) of generic/brand names known to interact.
KNOWN_INTERACTIONS: List[Dict] = [
    {"pair": ("warfarin", "aspirin"), "severity": "high",
     "message": "Increased bleeding risk when combined."},
    {"pair": ("ibuprofen", "aspirin"), "severity": "medium",
     "message": "May reduce cardioprotective effect of aspirin and raise GI bleeding risk."},
    {"pair": ("metformin", "alcohol"), "severity": "medium",
     "message": "Raised risk of lactic acidosis."},
    {"pair": ("sildenafil", "nitroglycerin"), "severity": "high",
     "message": "Can cause a dangerous drop in blood pressure."},
    {"pair": ("azithromycin", "warfarin"), "severity": "medium",
     "message": "May potentiate anticoagulant effect."},
    {"pair": ("simvastatin", "clarithromycin"), "severity": "high",
     "message": "Increased risk of muscle toxicity (rhabdomyolysis)."},
]

FREQUENCY_PATTERNS = {
    r"\bod\b|\bonce a day\b|\b1-0-0\b": "Once daily",
    r"\bbd\b|\btwice a day\b|\b1-0-1\b": "Twice daily",
    r"\btds\b|\bthrice a day\b|\b1-1-1\b": "Three times daily",
    r"\bqid\b|\bfour times a day\b": "Four times daily",
    r"\bhs\b|\bat bedtime\b": "At bedtime",
    r"\bsos\b|\bas needed\b|\bprn\b": "As needed",
}

DOSAGE_PATTERN = re.compile(r"(\d+\s?(?:mg|ml|mcg|g|iu))", re.IGNORECASE)


def _normalize(name: str) -> str:
    return name.strip().lower()


def parse_prescription_text(raw_text: str, known_medicines: List[Medicine]) -> List[Dict]:
    """
    Stand-in for OCR + LLM extraction. Splits the raw prescription text into
    lines, tries to pull a dosage + frequency out of each line, and fuzzy
    matches the leading words against the medicine catalog by substring match
    on name/generic_name. Each returned dict maps 1:1 to a PrescriptionItem.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    if not lines:
        # fall back to comma-separated single-line input
        lines = [l.strip() for l in raw_text.split(",") if l.strip()]

    catalog = {(_normalize(m.name)): m for m in known_medicines}
    catalog.update({(_normalize(m.generic_name)): m for m in known_medicines if m.generic_name})

    results = []
    for line in lines:
        dosage_match = DOSAGE_PATTERN.search(line)
        dosage = dosage_match.group(1) if dosage_match else None

        frequency = None
        for pattern, label in FREQUENCY_PATTERNS.items():
            if re.search(pattern, line, re.IGNORECASE):
                frequency = label
                break

        # Extracted name = text before the first digit / dosage token
        name_part = line
        if dosage_match:
            name_part = line[: dosage_match.start()]
        extracted_name = re.sub(r"[-,]", " ", name_part).strip() or line

        matched = None
        norm_extracted = _normalize(extracted_name)
        for key, med in catalog.items():
            if key and (key in norm_extracted or norm_extracted in key):
                matched = med
                break

        results.append({
            "extracted_name": extracted_name,
            "matched_medicine_id": matched.id if matched else None,
            "dosage": dosage,
            "frequency": frequency,
            "warning_flag": None if matched else "No exact catalog match - please verify manually",
        })

    return results


def check_drug_interactions(medicine_names: List[str]) -> List[Dict]:
    """Cross-checks a list of medicine/generic names against the static
    interaction table and returns any hits."""
    normalized = [_normalize(n) for n in medicine_names]
    hits = []
    for rule in KNOWN_INTERACTIONS:
        a, b = rule["pair"]
        if any(a in n for n in normalized) and any(b in n for n in normalized):
            hits.append({
                "medicines": [a, b],
                "severity": rule["severity"],
                "message": rule["message"],
            })
    return hits


def suggest_substitutes(medicine: Medicine, all_medicines: List[Medicine], limit: int = 5) -> List[Medicine]:
    """Suggests alternative medicines sharing the same generic name (true
    substitutes) or, failing that, the same category, excluding itself."""
    same_generic = [
        m for m in all_medicines
        if m.id != medicine.id and medicine.generic_name and m.generic_name
        and _normalize(m.generic_name) == _normalize(medicine.generic_name)
    ]
    if same_generic:
        return same_generic[:limit]

    same_category = [
        m for m in all_medicines
        if m.id != medicine.id and medicine.category and m.category
        and _normalize(m.category) == _normalize(medicine.category)
    ]
    return same_category[:limit]


def predict_expiry_risk(batch: Batch, warning_days: int = None) -> Dict:
    """Simple heuristic: risk grows as expiry approaches and as remaining
    quantity increases (more stock = more potential loss)."""
    warning_days = warning_days or settings.EXPIRY_WARNING_DAYS
    days_left = (batch.expiry_date - date.today()).days

    if days_left < 0:
        risk = "expired"
    elif days_left <= 14:
        risk = "critical"
    elif days_left <= warning_days:
        risk = "high" if batch.quantity > 50 else "medium"
    elif days_left <= warning_days * 2:
        risk = "low"
    else:
        risk = "none"

    return {
        "batch_id": batch.id,
        "days_left": days_left,
        "quantity": batch.quantity,
        "risk_level": risk,
    }


def forecast_demand(db: Session, medicine_id: int, lookback_days: int = 30) -> Dict:
    """Very small moving-average forecast based on historical stock_out
    movements, as a stand-in for a proper LLM/ML demand-forecasting model."""
    since = datetime.utcnow() - timedelta(days=lookback_days)
    movements = (
        db.query(StockMovement)
        .filter(
            StockMovement.medicine_id == medicine_id,
            StockMovement.movement_type == MovementType.stock_out,
            StockMovement.created_at >= since,
        )
        .all()
    )
    total_sold = sum(m.quantity for m in movements)
    avg_daily = round(total_sold / lookback_days, 2) if lookback_days else 0
    projected_next_30_days = round(avg_daily * 30)

    return {
        "medicine_id": medicine_id,
        "lookback_days": lookback_days,
        "total_sold_in_period": total_sold,
        "avg_daily_demand": avg_daily,
        "projected_demand_next_30_days": projected_next_30_days,
    }
