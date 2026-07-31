from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, EmailStr, ConfigDict

from .models import UserRole, POStatus, PrescriptionStatus, MovementType, AlertType, PaymentStatus


# ---------- Auth / Users ----------
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.staff


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str]
    role: UserRole
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    username: str


# ---------- Supplier ----------
class SupplierBase(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: int = 7


class SupplierCreate(SupplierBase):
    pass


class SupplierOut(SupplierBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Medicine ----------
class MedicineBase(BaseModel):
    name: str
    generic_name: Optional[str] = None
    category: Optional[str] = None
    dosage_form: Optional[str] = None
    manufacturer: Optional[str] = None
    gst_rate: float = 5.0
    storage_requirement: str = "Room temperature"
    unit_price: float
    reorder_level: int = 20


class MedicineCreate(MedicineBase):
    pass


class MedicineOut(MedicineBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    total_stock: Optional[int] = 0


# ---------- Batch ----------
class BatchBase(BaseModel):
    medicine_id: int
    batch_number: str
    quantity: int
    cost_price: float = 0.0
    manufacture_date: Optional[date] = None
    expiry_date: date
    supplier_id: Optional[int] = None


class BatchCreate(BatchBase):
    pass


class BatchOut(BatchBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    received_date: datetime


# ---------- Purchase Orders ----------
class POItemCreate(BaseModel):
    medicine_id: int
    quantity: int
    unit_cost: float


class POItemOut(POItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    expected_date: Optional[date] = None
    items: List[POItemCreate]


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_id: int
    status: POStatus
    order_date: datetime
    expected_date: Optional[date]
    total_amount: float
    items: List[POItemOut] = []


# ---------- Customer ----------
class CustomerBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Prescription ----------
class PrescriptionCreate(BaseModel):
    customer_id: Optional[int] = None
    raw_text: str  # typed-in or OCR-extracted text


class PrescriptionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    extracted_name: str
    matched_medicine_id: Optional[int]
    dosage: Optional[str]
    frequency: Optional[str]
    warning_flag: Optional[str]


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: Optional[int]
    raw_text: str
    status: PrescriptionStatus
    created_at: datetime
    items: List[PrescriptionItemOut] = []


class PrescriptionReview(BaseModel):
    status: PrescriptionStatus


# ---------- Billing ----------
class InvoiceItemCreate(BaseModel):
    medicine_id: int
    batch_id: int
    quantity: int


class InvoiceCreate(BaseModel):
    customer_id: Optional[int] = None
    prescription_id: Optional[int] = None
    discount_amount: float = 0.0
    items: List[InvoiceItemCreate]


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    medicine_id: int
    batch_id: int
    quantity: int
    unit_price: float
    subtotal: float


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: Optional[int]
    discount_amount: float
    tax_amount: float
    total_amount: float
    payment_status: PaymentStatus
    created_at: datetime
    items: List[InvoiceItemOut] = []


# ---------- Stock / Alerts ----------
class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    medicine_id: int
    batch_id: Optional[int]
    movement_type: MovementType
    quantity: int
    reference_type: Optional[str]
    reference_id: Optional[int]
    created_at: datetime


class StockAdjustment(BaseModel):
    medicine_id: int
    batch_id: int
    quantity: int
    reason: str


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: AlertType
    medicine_id: Optional[int]
    batch_id: Optional[int]
    message: str
    severity: str
    resolved: bool
    created_at: datetime


# ---------- AI ----------
class InteractionCheckRequest(BaseModel):
    medicine_names: List[str]


class SubstituteRequest(BaseModel):
    medicine_id: int
