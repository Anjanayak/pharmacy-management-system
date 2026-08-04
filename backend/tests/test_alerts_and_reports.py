def test_scan_creates_low_stock_alert(client, admin_headers, sample_medicine):
    # sample_medicine has reorder_level=20 and 0 stock -> should trigger a low_stock alert
    resp = client.post("/api/alerts/scan", headers=admin_headers)
    assert resp.status_code == 200
    types = [a["type"] for a in resp.json()]
    assert "low_stock" in types


def test_scan_is_idempotent_no_duplicate_alerts(client, admin_headers, sample_medicine):
    first = client.post("/api/alerts/scan", headers=admin_headers).json()
    second = client.post("/api/alerts/scan", headers=admin_headers).json()
    assert len(first) >= 1
    assert len(second) == 0  # nothing new since the same condition was already flagged


def test_list_alerts_returns_unresolved_only(client, admin_headers, sample_medicine):
    client.post("/api/alerts/scan", headers=admin_headers)
    resp = client.get("/api/alerts?resolved=false", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_resolve_alert_removes_it_from_unresolved_list(client, admin_headers, sample_medicine):
    alerts = client.post("/api/alerts/scan", headers=admin_headers).json()
    alert_id = alerts[0]["id"]

    resp = client.patch(f"/api/alerts/{alert_id}/resolve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True

    remaining = client.get("/api/alerts?resolved=false", headers=admin_headers).json()
    assert alert_id not in [a["id"] for a in remaining]


def test_reorder_needs_report_flags_low_stock_medicine(client, admin_headers, sample_medicine):
    resp = client.get("/api/reports/reorder-needs", headers=admin_headers)
    assert resp.status_code == 200
    ids = [r["medicine_id"] for r in resp.json()]
    assert sample_medicine["id"] in ids


def test_daily_sales_report_reflects_invoice(client, admin_headers, sample_medicine, sample_batch):
    client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 2}],
    }, headers=admin_headers)

    resp = client.get("/api/reports/daily-sales", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["invoice_count"] >= 1


def test_pharmacist_workload_report_tracks_activity(client, admin_headers, sample_medicine, sample_batch):
    client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 1}],
    }, headers=admin_headers)
    client.post("/api/prescriptions", json={"raw_text": "Paracetamol 500mg 1-0-1"}, headers=admin_headers)

    resp = client.get("/api/reports/pharmacist-workload", headers=admin_headers)
    assert resp.status_code == 200
    staff_entry = next((s for s in resp.json()["staff"] if s["username"] == "test_admin"), None)
    assert staff_entry is not None
    assert staff_entry["invoices_generated"] >= 1
    assert staff_entry["prescriptions_processed"] >= 1


def test_fast_moving_and_dead_stock_reports_smoke(client, admin_headers, sample_medicine, sample_batch):
    resp1 = client.get("/api/reports/fast-moving", headers=admin_headers)
    assert resp1.status_code == 200

    resp2 = client.get("/api/reports/dead-stock", headers=admin_headers)
    assert resp2.status_code == 200

    resp3 = client.get("/api/reports/expiry-loss", headers=admin_headers)
    assert resp3.status_code == 200
    assert "total_estimated_loss" in resp3.json()
