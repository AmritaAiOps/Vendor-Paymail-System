# Vendor Payment Reconciliation: Email Automation

Internal tool for Sudhamayi Enterprises Pvt. Ltd. The interface between the two tracks is in [docs/CONTRACT.md](docs/CONTRACT.md).

## Backend (dev)

```
cd backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload
.venv/Scripts/python -m pytest -q
```

API docs: http://localhost:8000/docs
