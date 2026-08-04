def test_create_and_get_medicine(client, admin_headers, sample_medicine):
    resp = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Paracetamol 500mg"
    assert resp.json()["total_stock"] == 0  # no batches yet


def test_medicine_total_stock_reflects_batches(client, admin_headers, sample_medicine, sample_batch):
    resp = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert resp.json()["total_stock"] == 100


def test_search_medicines_by_name(client, admin_headers, sample_medicine):
    resp = client.get("/api/medicines?search=Paracetamol", headers=admin_headers)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()]
    assert "Paracetamol 500mg" in names

    resp2 = client.get("/api/medicines?search=Nonexistent", headers=admin_headers)
    assert resp2.json() == []


def test_medicines_pagination_limit(client, admin_headers):
    for i in range(5):
        r = client.post("/api/medicines", json={"name": f"Med {i}", "unit_price": 1.0}, headers=admin_headers)
        assert r.status_code == 201

    resp = client.get("/api/medicines?limit=2&skip=0", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = client.get("/api/medicines?limit=2&skip=2", headers=admin_headers)
    assert len(resp2.json()) == 2
    # different page should return different items
    assert {m["id"] for m in resp.json()}.isdisjoint({m["id"] for m in resp2.json()})


def test_deactivated_medicine_hidden_from_list(client, admin_headers, sample_medicine):
    resp = client.delete(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert resp.status_code == 204

    resp2 = client.get("/api/medicines", headers=admin_headers)
    assert sample_medicine["id"] not in [m["id"] for m in resp2.json()]


def test_add_batch_records_stock_in_movement(client, admin_headers, sample_medicine, sample_batch):
    resp = client.get(f"/api/stock/movements?medicine_id={sample_medicine['id']}", headers=admin_headers)
    assert resp.status_code == 200
    movements = resp.json()
    assert any(m["movement_type"] == "stock_in" and m["quantity"] == 100 for m in movements)


def test_low_stock_endpoint_flags_medicine_below_reorder_level(client, admin_headers, sample_medicine):
    # sample_medicine has reorder_level=20 and no stock yet -> should be flagged
    resp = client.get("/api/medicines/alerts/low-stock", headers=admin_headers)
    assert resp.status_code == 200
    ids = [m["medicine_id"] for m in resp.json()]
    assert sample_medicine["id"] in ids


def test_low_stock_endpoint_excludes_well_stocked_medicine(client, admin_headers, sample_medicine, sample_batch):
    # sample_batch adds 100 units, well above reorder_level=20
    resp = client.get("/api/medicines/alerts/low-stock", headers=admin_headers)
    ids = [m["medicine_id"] for m in resp.json()]
    assert sample_medicine["id"] not in ids


def test_expiring_batches_endpoint(client, admin_headers, sample_medicine):
    from datetime import date, timedelta
    near_expiry = (date.today() + timedelta(days=10)).isoformat()

    resp = client.post("/api/medicines/batches", json={
        "medicine_id": sample_medicine["id"],
        "batch_number": "EXP-SOON",
        "quantity": 10,
        "expiry_date": near_expiry,
    }, headers=admin_headers)
    assert resp.status_code == 201

    resp2 = client.get("/api/medicines/alerts/expiring?days=30", headers=admin_headers)
    assert resp2.status_code == 200
    batch_numbers = [b["batch_number"] for b in resp2.json()]
    assert "EXP-SOON" in batch_numbers


def test_manual_stock_adjustment(client, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/stock/adjust", json={
        "medicine_id": sample_medicine["id"],
        "batch_id": sample_batch["id"],
        "quantity": -10,
        "reason": "Damaged in transit",
    }, headers=admin_headers)
    assert resp.status_code == 201

    check = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert check.json()["total_stock"] == 90


def test_stock_adjustment_cannot_go_negative(client, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/stock/adjust", json={
        "medicine_id": sample_medicine["id"],
        "batch_id": sample_batch["id"],
        "quantity": -1000,
        "reason": "Too much",
    }, headers=admin_headers)
    assert resp.status_code == 400
