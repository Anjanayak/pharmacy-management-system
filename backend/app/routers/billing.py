from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles

router = APIRouter(prefix="/api/customers", tags=["Customers"])
invoice_router = APIRouter(prefix="/api/invoices", tags=["Billing"])


@router.get("", response_model=List[schemas.CustomerOut])
def list_customers(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Customer).all()


@router.post("", response_model=schemas.CustomerOut, status_code=201)
def create_customer(
    payload: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    customer = models.Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@invoice_router.get("", response_model=List[schemas.InvoiceOut])
def list_invoices(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Invoice).order_by(models.Invoice.created_at.desc()).all()


@invoice_router.post("", response_model=schemas.InvoiceOut, status_code=201)
def create_invoice(
    payload: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    """Generates an invoice, validates stock availability per batch, deducts
    stock, and logs a stock_out movement for each line item (partial
    fulfillment must be handled by the caller sending only available
    quantities per batch)."""
    if not payload.items:
        raise HTTPException(400, "Invoice must contain at least one item")

    subtotal = 0.0
    tax_total = 0.0
    line_records = []

    for item in payload.items:
        medicine = db.get(models.Medicine, item.medicine_id)
        batch = db.get(models.Batch, item.batch_id)
        if not medicine or not batch or batch.medicine_id != medicine.id:
            raise HTTPException(404, f"Medicine/batch mismatch for medicine_id={item.medicine_id}")
        if batch.quantity < item.quantity:
            raise HTTPException(400, f"Insufficient stock in batch {batch.batch_number} for {medicine.name}")

        unit_price = medicine.unit_price
        line_subtotal = unit_price * item.quantity
        line_tax = line_subtotal * (medicine.gst_rate / 100)
        subtotal += line_subtotal
        tax_total += line_tax

        batch.quantity -= item.quantity
        line_records.append((item, unit_price, line_subtotal))

    total = subtotal + tax_total - payload.discount_amount

    invoice = models.Invoice(
        customer_id=payload.customer_id,
        prescription_id=payload.prescription_id,
        created_by=current_user.id,
        discount_amount=payload.discount_amount,
        tax_amount=round(tax_total, 2),
        total_amount=round(total, 2),
    )
    db.add(invoice)
    db.flush()

    for item, unit_price, line_subtotal in line_records:
        db.add(models.InvoiceItem(
            invoice_id=invoice.id,
            medicine_id=item.medicine_id,
            batch_id=item.batch_id,
            quantity=item.quantity,
            unit_price=unit_price,
            subtotal=round(line_subtotal, 2),
        ))
        db.add(models.StockMovement(
            medicine_id=item.medicine_id,
            batch_id=item.batch_id,
            movement_type=models.MovementType.stock_out,
            quantity=item.quantity,
            reference_type="invoice",
            reference_id=invoice.id,
        ))

    db.commit()
    db.refresh(invoice)
    return invoice


@invoice_router.get("/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return invoice


@invoice_router.post("/items/{invoice_item_id}/return", status_code=201)
def return_invoice_item(
    invoice_item_id: int,
    quantity: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    line = db.get(models.InvoiceItem, invoice_item_id)
    if not line:
        raise HTTPException(404, "Invoice item not found")
    if quantity > line.quantity:
        raise HTTPException(400, "Return quantity exceeds sold quantity")

    batch = db.get(models.Batch, line.batch_id)
    batch.quantity += quantity

    db.add(models.ReturnRecord(invoice_item_id=invoice_item_id, quantity=quantity, reason=reason))
    db.add(models.StockMovement(
        medicine_id=line.medicine_id,
        batch_id=line.batch_id,
        movement_type=models.MovementType.return_,
        quantity=quantity,
        reference_type="return",
        reference_id=invoice_item_id,
    ))
    db.commit()
    return {"message": "Return processed", "invoice_item_id": invoice_item_id, "quantity": quantity}