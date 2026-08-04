# Pharmacy Management System (AI-enabled)

A full-stack pharmacy operations platform: medicine catalog, batch/expiry tracking,
prescription intake with AI-assisted extraction and interaction checking, billing,
supplier & purchase-order management, expiry/low-stock alerts, and reporting.

Built to run entirely on your machine with **no external API key required** — the
"AI layer" ships as a rule-based engine (see `backend/app/services/ai_service.py`)
that you can later swap for a real OpenAI/Anthropic/local-LLM call without touching
any router code.

---

## Stack

| Layer      | Technology |
|------------|------------|
| Backend    | FastAPI + SQLAlchemy, JWT auth, RBAC (admin/manager/staff/customer) |
| Database   | PostgreSQL 16 (via Docker) |
| Frontend   | Plain HTML/CSS/JS dashboard (no build step) |
| AI layer   | Rule-based prescription parsing, drug-interaction checks, substitute suggestion, expiry-risk scoring, simple demand forecasting |
| DevOps     | Dockerfile + docker-compose for backend + Postgres |

---

## 1. Run the backend + database

Requires Docker Desktop (or Docker Engine + Compose) installed.

```bash
cd pharmacy-system
docker-compose up --build
```

This starts:
- `pharmacy_db` — Postgres on `localhost:5432`
- `pharmacy_backend` — FastAPI on `localhost:8000`

The first time it starts, the database is empty. Seed it with demo data
(medicines, suppliers, batches — some deliberately near-expiry/low-stock so
the Alerts screen has something to show) by running, in a **second terminal**:

```bash
docker exec -it pharmacy_backend python -m app.seed
```

You should see:
```
Seed data created successfully.
Login with: admin/admin123, manager/manager123, staff/staff123
```

Verify the API is up: open **http://localhost:8000/docs** for interactive
Swagger/OpenAPI documentation of every endpoint.

### Running the backend without Docker (optional)
If you'd rather run Postgres and FastAPI natively:
```bash
# 1. Start your own local Postgres and create a DB named pharmacy_db
# 2. cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://<user>:<pass>@localhost:5432/pharmacy_db
export JWT_SECRET_KEY=some_secret
python -m app.seed
uvicorn app.main:app --reload
```

---

## 2. Run the frontend

The frontend is static HTML/JS — no build step. Two options:

**Option A — just open the file:**
Double-click `frontend/index.html` (or open it via `File > Open` in your browser).

**Option B — serve it (recommended, avoids some browsers' file:// quirks):**
```bash
cd frontend
python -m http.server 5500
```
Then visit **http://localhost:5500**.

Either way, the frontend talks to the backend at `http://localhost:8000`
(see `API_BASE` in `frontend/js/api.js` — change it if you deploy the backend
elsewhere).

Log in with one of the seeded accounts:
| Username | Password    | Role    |
|----------|-------------|---------|
| admin    | admin123    | admin   |
| manager  | manager123  | manager |
| staff    | staff123    | staff   |

---

## 3. What's implemented

- **Medicine catalog** — CRUD with category, dosage form, manufacturer, GST rate, reorder level
- **Batch-wise inventory** — batch numbers, expiry dates, cost price, stock-in movement logging
- **Prescription intake + AI assist** — optionally upload a prescription image for offline OCR (Tesseract, no API key/internet needed), or paste/type text directly → rule-based
  extraction of medicine name / dosage / frequency, catalog matching, and
  drug-interaction flagging (see `KNOWN_INTERACTIONS` table — extend freely)
- **Billing** — multi-item invoices, automatic per-batch stock deduction, GST calculation,
  discounts, returns with stock restoration
- **Suppliers & Purchase Orders** — create POs, mark received
- **Expiry & low-stock alert engine** — `POST /api/alerts/scan` scans all batches/medicines
  and raises alerts; wire this to a cron job or background worker for production
- **Reports** — fast-moving medicines, dead stock, expiry loss estimate, daily sales, reorder needs
- **RBAC** — admin/manager/staff/customer roles enforced at the API layer via JWT
- **Audit-log table** exists in the schema (`models.AuditLog`) — hook it into routers as needed
- **API docs** — full Swagger UI at `/docs`, ReDoc at `/redoc`

## 4. Where to plug in a real LLM later

Everything AI-related lives in `backend/app/services/ai_service.py`. Each function
(`parse_prescription_text`, `check_drug_interactions`, `suggest_substitutes`,
`predict_expiry_risk`, `forecast_demand`) is a clean seam — swap the body for a call
to OpenAI/Anthropic/a LangChain pipeline (e.g. real OCR + NER for prescriptions, a
vector-store-backed RAG chatbot over your SOPs) without changing any router.

**This is now implemented as an optional, opt-in path** using Groq's free,
OpenAI-compatible API (`backend/app/services/llm_service.py`). To enable it:

1. Get a free API key from [console.groq.com](https://console.groq.com) → API Keys.
2. In the project root (same folder as `docker-compose.yml`), copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` and paste your key:
   ```
   GROQ_API_KEY=gsk_your_key_here
   ```
4. Rebuild: `docker-compose down -v && docker-compose up --build`.

That's it — `POST /api/prescriptions` will now use the real LLM for medicine/dosage/frequency
extraction and drug-interaction checking instead of the rule-based engine. Catalog
matching still happens locally against your own medicine data either way. If the
API call ever fails (bad key, rate limit, network issue), the app automatically
falls back to the offline rule-based layer for that request rather than erroring out.

Leaving `.env` unset (or not creating it at all) keeps the app on the free,
offline rule-based layer — this is the default and needs no setup.

## 5. Project structure

```
pharmacy-system/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # FastAPI app + router registration
│       ├── config.py          # settings from env vars
│       ├── database.py        # SQLAlchemy engine/session
│       ├── models.py          # all ORM models
│       ├── schemas.py         # Pydantic request/response models
│       ├── auth.py            # JWT + password hashing + RBAC dependency
│       ├── seed.py            # demo data loader
│       ├── routers/           # one router per domain area
│       └── services/
│           └── ai_service.py  # rule-based AI layer (LLM-swappable)
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/
        ├── api.js             # fetch wrapper + typed API calls
        └── app.js             # views, forms, rendering
```

## 6. Running the automated test suite

The backend ships with a pytest suite (`backend/tests/`) covering auth/RBAC,
refresh tokens, medicines/batches/pagination, billing (including atomic
stock-deduction and insufficient-stock rejection), prescriptions/AI parsing,
drug-interaction detection, substitute suggestions, the alert-scan engine,
and all six reports. It runs against a disposable SQLite database — no
PostgreSQL or Docker required to run tests, though running them inside the
container works too since `pytest`/`httpx` are already in requirements.txt.

**From inside the running container (simplest, no local Python needed):**
```bash
docker exec -it pharmacy_backend pytest
```

**Locally, if you have Python 3.11 set up:**
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest
```

Each test function gets a freshly created and torn-down schema for full
isolation, so tests can run in any order and don't depend on the seed data.

## 7. Next steps toward the full brief

The original project spec also calls for: a real LLM swap-in for the AI
layer (currently rule-based/offline — the seam is `backend/app/services/ai_service.py`),
a RAG chatbot over pharmacy SOPs (add `chromadb`/`pinecone` + LangChain and a new
`/api/ai/chat` route), CI/CD via GitHub Actions, and AWS deployment. Prescription
OCR is now implemented offline via Tesseract (`POST /api/prescriptions/extract-text`),
and an automated pytest suite now covers the core backend (see Section 7).
The architecture here (routers + services + models) is deliberately structured so
each remaining item can be added as a new router/service without refactoring
existing code.
