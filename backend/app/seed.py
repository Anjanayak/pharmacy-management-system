"""
Run with:  python -m app.seed
Populates demo users, suppliers, medicines and batches so the app is usable
immediately after `docker-compose up`.
"""
from datetime import date, timedelta

from .database import SessionLocal, Base, engine
from . import models
from .auth import hash_password

Base.metadata.create_all(bind=engine)


def run():
    db = SessionLocal()
    try:
        if db.query(models.User).first():
            print("Database already seeded. Skipping.")
            return

        # ---- Users ----
        users = [
            models.User(username="admin", email="admin@pharmacy.local", full_name="System Admin",
                        role=models.UserRole.admin, hashed_password=hash_password("admin123")),
            models.User(username="manager", email="manager@pharmacy.local", full_name="Store Manager",
                        role=models.UserRole.manager, hashed_password=hash_password("manager123")),
            models.User(username="staff", email="staff@pharmacy.local", full_name="Pharmacy Staff",
                        role=models.UserRole.staff, hashed_password=hash_password("staff123")),
        ]
        db.add_all(users)
        db.flush()

        # ---- Suppliers ----
        supplier1 = models.Supplier(name="MedSource Distributors", contact_person="R. Kumar",
                                     phone="9876543210", email="sales@medsource.example", lead_time_days=5)
        supplier2 = models.Supplier(name="HealthLine Pharma Supplies", contact_person="A. Rao",
                                     phone="9123456780", email="orders@healthline.example", lead_time_days=7)
        db.add_all([supplier1, supplier2])
        db.flush()

        # ---- Medicines ----
        medicines_data = [
            dict(name="Paracetamol 500mg", generic_name="Paracetamol", category="Analgesic",
                 dosage_form="Tablet", manufacturer="Cipla", unit_price=2.5, reorder_level=100),
            dict(name="Crocin 650", generic_name="Paracetamol", category="Analgesic",
                 dosage_form="Tablet", manufacturer="GSK", unit_price=3.0, reorder_level=50),
            dict(name="Aspirin 75mg", generic_name="Aspirin", category="Antiplatelet",
                 dosage_form="Tablet", manufacturer="Bayer", unit_price=1.5, reorder_level=60),
            dict(name="Warfarin 5mg", generic_name="Warfarin", category="Anticoagulant",
                 dosage_form="Tablet", manufacturer="Sun Pharma", unit_price=6.0, reorder_level=20),
            dict(name="Metformin 500mg", generic_name="Metformin", category="Antidiabetic",
                 dosage_form="Tablet", manufacturer="Dr. Reddy's", unit_price=2.0, reorder_level=80),
            dict(name="Azithromycin 500mg", generic_name="Azithromycin", category="Antibiotic",
                 dosage_form="Tablet", manufacturer="Cipla", unit_price=12.0, reorder_level=30),
            dict(name="Ibuprofen 400mg", generic_name="Ibuprofen", category="NSAID",
                 dosage_form="Tablet", manufacturer="Abbott", unit_price=2.2, reorder_level=70),
            dict(name="Cough Syrup DX", generic_name="Dextromethorphan", category="Antitussive",
                 dosage_form="Syrup", manufacturer="Himalaya", unit_price=45.0, reorder_level=25),
            dict(name="Amoxicillin 250mg", generic_name="Amoxicillin", category="Antibiotic",
                 dosage_form="Capsule", manufacturer="Cipla", unit_price=8.0, reorder_level=40),
            dict(name="Simvastatin 20mg", generic_name="Simvastatin", category="Statin",
                 dosage_form="Tablet", manufacturer="Sun Pharma", unit_price=5.5, reorder_level=30),
        ]
        medicines = [models.Medicine(**m) for m in medicines_data]
        db.add_all(medicines)
        db.flush()

        # ---- Batches (mix of healthy, low, and near/expired stock for demo alerts) ----
        today = date.today()
        batch_plan = [
            (0, "PCM-A1", 300, today + timedelta(days=400), 1.5),
            (1, "CRC-B1", 15, today + timedelta(days=20), 2.0),     # near-expiry + low stock
            (2, "ASP-C1", 200, today + timedelta(days=500), 0.8),
            (3, "WAR-D1", 10, today + timedelta(days=300), 4.0),    # low stock
            (4, "MET-E1", 250, today + timedelta(days=250), 1.2),
            (5, "AZT-F1", 5, today - timedelta(days=5), 8.0),       # already expired
            (6, "IBU-G1", 180, today + timedelta(days=200), 1.4),
            (7, "SYR-H1", 40, today + timedelta(days=45), 30.0),    # near-expiry
            (8, "AMX-I1", 120, today + timedelta(days=180), 5.5),
            (9, "SIM-J1", 8, today + timedelta(days=150), 3.5),     # low stock
        ]
        for idx, batch_no, qty, expiry, cost in batch_plan:
            db.add(models.Batch(
                medicine_id=medicines[idx].id,
                batch_number=batch_no,
                quantity=qty,
                cost_price=cost,
                manufacture_date=today - timedelta(days=200),
                expiry_date=expiry,
                supplier_id=supplier1.id if idx % 2 == 0 else supplier2.id,
            ))

        # ---- Demo customer ----
        db.add(models.Customer(name="Walk-in Customer", phone="0000000000"))

        db.commit()
        print("Seed data created successfully.")
        print("Login with: admin/admin123, manager/manager123, staff/staff123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
