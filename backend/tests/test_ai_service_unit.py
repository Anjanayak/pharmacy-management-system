from datetime import date, timedelta
from types import SimpleNamespace

from app.services import ai_service


def _fake_medicine(id_, name, generic_name=None, category=None):
    return SimpleNamespace(id=id_, name=name, generic_name=generic_name, category=category)


def test_check_drug_interactions_detects_known_pair():
    hits = ai_service.check_drug_interactions(["Warfarin 5mg", "Aspirin 75mg"])
    assert len(hits) == 1
    assert hits[0]["severity"] == "high"


def test_check_drug_interactions_no_hit_for_unrelated_pair():
    hits = ai_service.check_drug_interactions(["Vitamin C 500mg", "Cough Syrup DX"])
    assert hits == []


def test_check_drug_interactions_case_insensitive():
    hits = ai_service.check_drug_interactions(["WARFARIN", "aspirin"])
    assert len(hits) == 1


def test_suggest_substitutes_prefers_same_generic_over_category():
    target = _fake_medicine(1, "Crocin 650", generic_name="Paracetamol", category="Analgesic")
    same_generic = _fake_medicine(2, "Paracetamol 500mg", generic_name="Paracetamol", category="Analgesic")
    same_category_only = _fake_medicine(3, "Ibuprofen 400mg", generic_name="Ibuprofen", category="Analgesic")

    result = ai_service.suggest_substitutes(target, [target, same_generic, same_category_only])
    assert same_generic in result
    assert same_category_only not in result  # same-generic match found, category fallback not needed


def test_suggest_substitutes_falls_back_to_category(): 
    target = _fake_medicine(1, "Unique Drug", generic_name="RareGeneric", category="NSAID")
    other = _fake_medicine(2, "Other NSAID", generic_name="DifferentGeneric", category="NSAID")

    result = ai_service.suggest_substitutes(target, [target, other])
    assert other in result


def test_predict_expiry_risk_classifies_expired_batch():
    batch = SimpleNamespace(id=1, expiry_date=date.today() - timedelta(days=5), quantity=10)
    risk = ai_service.predict_expiry_risk(batch)
    assert risk["risk_level"] == "expired"


def test_predict_expiry_risk_classifies_critical_batch():
    batch = SimpleNamespace(id=1, expiry_date=date.today() + timedelta(days=5), quantity=10)
    risk = ai_service.predict_expiry_risk(batch)
    assert risk["risk_level"] == "critical"


def test_predict_expiry_risk_classifies_safe_batch():
    batch = SimpleNamespace(id=1, expiry_date=date.today() + timedelta(days=200), quantity=10)
    risk = ai_service.predict_expiry_risk(batch)
    assert risk["risk_level"] == "none"


def test_parse_prescription_text_extracts_dosage_frequency_and_matches():
    catalog = [_fake_medicine(1, "Paracetamol 500mg", generic_name="Paracetamol")]
    results = ai_service.parse_prescription_text("Paracetamol 500mg 1-0-1", catalog)
    assert len(results) == 1
    assert results[0]["dosage"] == "500mg"
    assert results[0]["frequency"] == "Twice daily"
    assert results[0]["matched_medicine_id"] == 1


def test_parse_prescription_text_handles_multiple_lines():
    catalog = [_fake_medicine(1, "Warfarin 5mg"), _fake_medicine(2, "Aspirin 75mg")]
    results = ai_service.parse_prescription_text("Warfarin 5mg 1-0-0\nAspirin 75mg OD", catalog)
    assert len(results) == 2
    assert results[0]["matched_medicine_id"] == 1
    assert results[1]["matched_medicine_id"] == 2


def test_parse_prescription_text_flags_unmatched_medicine():
    results = ai_service.parse_prescription_text("UnknownDrug 10mg 1-0-0", [])
    assert results[0]["matched_medicine_id"] is None
    assert results[0]["warning_flag"] is not None
