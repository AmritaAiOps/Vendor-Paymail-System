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
.venv/Scripts/python -m scripts.seed_fixture   # optional: the three-row example data
.venv/Scripts/python -m uvicorn app.main:app --reload
.venv/Scripts/python -m pytest -q
```

API docs: http://localhost:8000/docs

## Contributing

Two people build in parallel. Person A owns the engine and Person B owns delivery; [docs/CONTRACT.md](docs/CONTRACT.md) says who owns what, and [.github/CODEOWNERS](.github/CODEOWNERS) mirrors it.

- Both people branch from the tag `foundation-v1`. Person A works on `backend`; Person B works on their own branch.
- Commit at the end of every phase, on your own branch.
- Nothing goes to `main` until the final merge.
- Never edit a folder you don't own. Shared files (contract, schemas, `main.py`, fixture, contract test) change only when both people agree.
- Only Person A writes Alembic migrations.
- Before finishing any phase, and again after the merge, run `.venv/Scripts/python -m pytest tests/contract -q` from `backend/`.

## Docker (app + Postgres)

```
cp .env.example .env   # set POSTGRES_PASSWORD
docker compose up --build
```
