from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas, models
from ..database import get_db
from ..auth import get_current_user, require_roles

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])


@router.get("", response_model=List[schemas.SupplierOut])
def list_suppliers(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Supplier).all()


@router.post("", response_model=schemas.SupplierOut, status_code=201)
def create_supplier(
    payload: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    supplier = models.Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/{supplier_id}", response_model=schemas.SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    supplier = db.query(models.Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    return supplier


# ---------- Purchase Orders ----------
po_router = APIRouter(prefix="/api/purchase-orders", tags=["Purchase Orders"])


@po_router.get("", response_model=List[schemas.PurchaseOrderOut])
def list_purchase_orders(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.PurchaseOrder).order_by(models.PurchaseOrder.order_date.desc()).all()


@po_router.post("", response_model=schemas.PurchaseOrderOut, status_code=201)
def create_purchase_order(
    payload: schemas.PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    supplier = db.query(models.Supplier).get(payload.supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")

    total = sum(item.quantity * item.unit_cost for item in payload.items)
    po = models.PurchaseOrder(
        supplier_id=payload.supplier_id,
        expected_date=payload.expected_date,
        total_amount=total,
        created_by=current_user.id,
    )
    db.add(po)
    db.flush()

    for item in payload.items:
        db.add(models.PurchaseOrderItem(
            purchase_order_id=po.id,
            medicine_id=item.medicine_id,
            quantity=item.quantity,
            unit_cost=item.unit_cost,
        ))

    db.commit()
    db.refresh(po)
    return po


@po_router.post("/{po_id}/receive", response_model=schemas.PurchaseOrderOut)
def receive_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager, models.UserRole.staff)),
):
    """Marks a PO as received. Actual batch creation (with batch numbers and
    expiry dates) should be done via POST /api/medicines/batches per item,
    since real-world receipts need per-item batch/expiry info from the
    supplier's delivery note."""
    po = db.query(models.PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Purchase order not found")
    po.status = models.POStatus.received
    db.commit()
    db.refresh(po)
    return po


@po_router.post("/{po_id}/cancel", response_model=schemas.PurchaseOrderOut)
def cancel_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.UserRole.admin, models.UserRole.manager)),
):
    po = db.query(models.PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Purchase order not found")
    po.status = models.POStatus.cancelled
    db.commit()
    db.refresh(po)
    return po
