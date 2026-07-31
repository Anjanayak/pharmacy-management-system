from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import auth, medicines, suppliers, prescriptions, billing, stock, ai

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Pharmacy Management System API",
    description="AI-enabled pharmacy operations platform: medicines, prescriptions, "
                "stock, billing, suppliers, purchase orders, expiry alerts, and AI assist.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(medicines.router)
app.include_router(suppliers.router)
app.include_router(suppliers.po_router)
app.include_router(prescriptions.router)
app.include_router(billing.router)
app.include_router(billing.invoice_router)
app.include_router(stock.router)
app.include_router(stock.alerts_router)
app.include_router(stock.reports_router)
app.include_router(ai.router)


@app.get("/")
def root():
    return {"message": "Pharmacy Management System API is running. Visit /docs for API documentation."}


@app.get("/health")
def health():
    return {"status": "ok"}
