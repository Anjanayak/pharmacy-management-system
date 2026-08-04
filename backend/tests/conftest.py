"""
Shared pytest fixtures for the backend test suite.

Sets DATABASE_URL to a local SQLite file *before* importing the app, so the
whole suite runs without needing a running PostgreSQL instance. Every test
function gets a freshly created and torn-down schema for full isolation.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_pharmacy.db")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_do_not_use_in_production")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine


@pytest.fixture(autouse=True)
def _reset_db():
    """Fresh schema before every test, dropped after — full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


# ---------- Auth helpers ----------

def register_user(client, username, password, role="staff", email=None, full_name=None):
    resp = client.post("/api/auth/register", json={
        "username": username,
        "email": email or f"{username}@test-demo.com",
        "password": password,
        "full_name": full_name or username.title(),
        "role": role,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client, username, password):
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client):
    register_user(client, "test_admin", "adminpass123", role="admin")
    token = login(client, "test_admin", "adminpass123")["access_token"]
    return auth_headers(token)


@pytest.fixture
def manager_headers(client):
    register_user(client, "test_manager", "managerpass123", role="manager")
    token = login(client, "test_manager", "managerpass123")["access_token"]
    return auth_headers(token)


@pytest.fixture
def staff_headers(client):
    register_user(client, "test_staff", "staffpass123", role="staff")
    token = login(client, "test_staff", "staffpass123")["access_token"]
    return auth_headers(token)


@pytest.fixture
def sample_medicine(client, admin_headers):
    """Creates one active medicine via the real API and returns its JSON."""
    resp = client.post("/api/medicines", json={
        "name": "Paracetamol 500mg",
        "generic_name": "Paracetamol",
        "category": "Analgesic",
        "dosage_form": "Tablet",
        "manufacturer": "Cipla",
        "gst_rate": 5.0,
        "unit_price": 2.5,
        "reorder_level": 20,
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def sample_batch(client, admin_headers, sample_medicine):
    resp = client.post("/api/medicines/batches", json={
        "medicine_id": sample_medicine["id"],
        "batch_number": "PCM-TEST-1",
        "quantity": 100,
        "cost_price": 1.5,
        "expiry_date": "2030-01-01",
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
