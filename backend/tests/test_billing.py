def test_invoice_deducts_stock_and_calculates_gst(client, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 10}],
    }, headers=admin_headers)
    assert resp.status_code == 201
    invoice = resp.json()

    # unit_price=2.5, gst_rate=5.0 -> subtotal=25.0, tax=1.25, total=26.25
    assert invoice["tax_amount"] == 1.25
    assert invoice["total_amount"] == 26.25
    assert len(invoice["items"]) == 1
    assert invoice["items"][0]["quantity"] == 10

    med = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert med.json()["total_stock"] == 90


def test_invoice_applies_discount(client, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 4}],
        "discount_amount": 2.0,
    }, headers=admin_headers)
    assert resp.status_code == 201
    invoice = resp.json()
    # subtotal=10.0, tax=0.5, total = 10.5 - 2.0 = 8.5
    assert invoice["total_amount"] == 8.5


def test_invoice_rejects_insufficient_stock(client, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 9999}],
    }, headers=admin_headers)
    assert resp.status_code == 400

    # confirm nothing was deducted despite the failed attempt
    med = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert med.json()["total_stock"] == 100


def test_invoice_all_or_nothing_across_multiple_items(client, admin_headers, sample_medicine, sample_batch):
    """If one line item in a multi-item invoice is invalid, none of the stock
    should be deducted for any line — the whole invoice must fail atomically."""
    resp = client.post("/api/medicines", json={"name": "Second Med", "unit_price": 1.0}, headers=admin_headers)
    med2 = resp.json()
    batch2 = client.post("/api/medicines/batches", json={
        "medicine_id": med2["id"], "batch_number": "B2", "quantity": 5, "expiry_date": "2030-01-01",
    }, headers=admin_headers).json()

    resp = client.post("/api/invoices", json={
        "items": [
            {"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 5},
            {"medicine_id": med2["id"], "batch_id": batch2["id"], "quantity": 9999},  # invalid
        ],
    }, headers=admin_headers)
    assert resp.status_code == 400

    med1_check = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert med1_check.json()["total_stock"] == 100  # untouched


def test_staff_can_generate_invoice(client, staff_headers, admin_headers, sample_medicine, sample_batch):
    resp = client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 1}],
    }, headers=staff_headers)
    assert resp.status_code == 201


def test_return_restores_stock(client, admin_headers, sample_medicine, sample_batch):
    invoice = client.post("/api/invoices", json={
        "items": [{"medicine_id": sample_medicine["id"], "batch_id": sample_batch["id"], "quantity": 20}],
    }, headers=admin_headers).json()
    invoice_item_id = invoice["items"][0]["id"]

    med_after_sale = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert med_after_sale.json()["total_stock"] == 80

    resp = client.post(
        f"/api/invoices/items/{invoice_item_id}/return",
        params={"quantity": 5, "reason": "Customer changed mind"},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    med_after_return = client.get(f"/api/medicines/{sample_medicine['id']}", headers=admin_headers)
    assert med_after_return.json()["total_stock"] == 85
