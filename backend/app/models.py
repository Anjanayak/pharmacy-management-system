import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey,
    Enum, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    staff = "staff"
    customer = "customer"


class POStatus(str, enum.Enum):
    pending = "pending"
    received = "received"
    cancelled = "cancelled"


class PrescriptionStatus(str, enum.Enum):
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class MovementType(str, enum.Enum):
    stock_in = "stock_in"
    stock_out = "stock_out"
    return_ = "return"
    damage = "damage"
    adjustment = "adjustment"


class AlertType(str, enum.Enum):
    expiry = "expiry"
    low_stock = "low_stock"
    interaction = "interaction"


class PaymentStatus(str, enum.Enum):
    paid = "paid"
    partial = "partial"
    pending = "pending"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(120))
    role = Column(Enum(UserRole), default=UserRole.staff, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    contact_person = Column(String(120))
    phone = Column(String(30))
    email = Column(String(120))
    address = Column(String(255))
    lead_time_days = Column(Integer, default=7)
    created_at = Column(DateTime, default=datetime.utcnow)

    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    generic_name = Column(String(150), index=True)
    category = Column(String(80))
    dosage_form = Column(String(50))  # tablet, syrup, injection, etc.
    manufacturer = Column(String(120))
    gst_rate = Column(Float, default=5.0)
    storage_requirement = Column(String(120), default="Room temperature")
    unit_price = Column(Float, nullable=False, default=0.0)
    reorder_level = Column(Integer, default=20)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("Batch", back_populates="medicine")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_number = Column(String(80), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    cost_price = Column(Float, default=0.0)
    manufacture_date = Column(Date)
    expiry_date = Column(Date, nullable=False)
    received_date = Column(DateTime, default=datetime.utcnow)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)

    __table_args__ = (UniqueConstraint("medicine_id", "batch_number", name="uq_medicine_batch"),)

    medicine = relationship("Medicine", back_populates="batches")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    status = Column(Enum(POStatus), default=POStatus.pending)
    order_date = Column(DateTime, default=datetime.utcnow)
    expected_date = Column(Date, nullable=True)
    total_amount = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    medicine = relationship("Medicine")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(30))
    email = Column(String(120))
    address = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    raw_text = Column(Text)  # OCR/typed-in prescription text
    status = Column(Enum(PrescriptionStatus), default=PrescriptionStatus.pending_review)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    extracted_name = Column(String(150))
    matched_medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)
    dosage = Column(String(80))
    frequency = Column(String(80))
    warning_flag = Column(String(255), nullable=True)

    prescription = relationship("Prescription", back_populates="items")
    matched_medicine = relationship("Medicine")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=True)
    discount_amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.paid)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    invoice = relationship("Invoice", back_populates="items")
    medicine = relationship("Medicine")
    batch = relationship("Batch")


class ReturnRecord(Base):
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True, index=True)
    invoice_item_id = Column(Integer, ForeignKey("invoice_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    reason = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
    movement_type = Column(Enum(MovementType), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference_type = Column(String(50), nullable=True)  # invoice, purchase_order, return, manual
    reference_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    medicine = relationship("Medicine")
    batch = relationship("Batch")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(Enum(AlertType), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)
    message = Column(String(255), nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    medicine = relationship("Medicine")
    batch = relationship("Batch")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False)
    entity = Column(String(80), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
