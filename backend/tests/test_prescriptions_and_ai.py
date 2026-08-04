def test_prescription_extracts_dosage_and_frequency_and_matches_catalog(client, admin_headers, sample_medicine):
    resp = client.post("/api/prescriptions", json={
        "raw_text": "Paracetamol 500mg 1-0-1",
    }, headers=admin_headers)
    assert resp.status_code == 201
    prescription = resp.json()
    assert prescription["status"] == "pending_review"
    assert len(prescription["items"]) == 1

    item = prescription["items"][0]
    assert item["dosage"] == "500mg"
    assert item["frequency"] == "Twice daily"
    assert item["matched_medicine_id"] == sample_medicine["id"]


def test_prescription_flags_known_drug_interaction(client, admin_headers):
    client.post("/api/medicines", json={"name": "Warfarin 5mg", "generic_name": "Warfarin", "unit_price": 6.0}, headers=admin_headers)
    client.post("/api/medicines", json={"name": "Aspirin 75mg", "generic_name": "Aspirin", "unit_price": 1.5}, headers=admin_headers)

    resp = client.post("/api/prescriptions", json={
        "raw_text": "Warfarin 5mg 1-0-0\nAspirin 75mg OD",
    }, headers=admin_headers)
    assert resp.status_code == 201
    items = resp.json()["items"]
    assert len(items) == 2
    assert all("Interaction risk" in (it["warning_flag"] or "") for it in items)


def test_prescription_no_interaction_when_unrelated_medicines(client, admin_headers, sample_medicine):
    resp = client.post("/api/prescriptions", json={
        "raw_text": "Paracetamol 500mg 1-0-1",
    }, headers=admin_headers)
    item = resp.json()["items"][0]
    assert item["warning_flag"] is None or "Interaction risk" not in (item["warning_flag"] or "")


def test_prescription_unmatched_medicine_gets_manual_review_flag(client, admin_headers):
    resp = client.post("/api/prescriptions", json={
        "raw_text": "SomeMedicineNotInCatalog 10mg 1-0-0",
    }, headers=admin_headers)
    item = resp.json()["items"][0]
    assert item["matched_medicine_id"] is None
    assert "verify manually" in (item["warning_flag"] or "").lower()


def test_review_prescription_updates_status(client, admin_headers, sample_medicine):
    prescription = client.post("/api/prescriptions", json={
        "raw_text": "Paracetamol 500mg 1-0-1",
    }, headers=admin_headers).json()

    resp = client.patch(f"/api/prescriptions/{prescription['id']}/review", json={"status": "approved"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_ai_check_interactions_endpoint_direct(client, admin_headers):
    resp = client.post("/api/ai/check-interactions", json={
        "medicine_names": ["warfarin 5mg", "aspirin 75mg"],
    }, headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()["interactions_found"]) >= 1


def test_ai_substitutes_endpoint_matches_same_generic(client, admin_headers):
    client.post("/api/medicines", json={"name": "Crocin 650", "generic_name": "Paracetamol", "unit_price": 3.0}, headers=admin_headers)
    med2 = client.post("/api/medicines", json={"name": "Paracetamol 500mg", "generic_name": "Paracetamol", "unit_price": 2.5}, headers=admin_headers).json()

    resp = client.post("/api/ai/substitutes", json={"medicine_id": med2["id"]}, headers=admin_headers)
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["substitutes"]]
    assert "Crocin 650" in names
