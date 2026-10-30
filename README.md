# Vendor Payment Reconciliation: Email Automation

Internal tool for Sudhamayi Enterprises Pvt. Ltd. The interface between the two tracks is in [docs/CONTRACT.md](docs/CONTRACT.md).

Layout: `backend/` (FastAPI, Person A + B), `frontend/` (React + Vite, Person B).
`.env.example` and `backend/requirements.txt` have `# --- A ---` / `# --- B ---` blocks. Edit only your own block.

## Backend (dev, SQLite)

```
cp .env.example .env
cd backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m uvicorn app.main:app --reload
.venv/Scripts/python -m pytest -q
```

API docs: http://localhost:8000/docs

## Docker (app + Postgres)

```
cp .env.example .env   # set POSTGRES_PASSWORD and SECRET_KEY
docker compose up --build
```
