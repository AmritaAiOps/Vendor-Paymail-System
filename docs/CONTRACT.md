# Contract: Person A (Engine) ↔ Person B (Delivery)

Frozen at tag `foundation-v1`. Any change: stop, write it up, both people agree, update this file **and** `backend/tests/test_contract.py` in the same commit. Nobody changes it silently.

Enforced by `backend/tests/test_contract.py`. Run it before calling any phase finished:

```
cd backend && .venv/Scripts/python -m pytest tests/test_contract.py -q
```

## 1. Ownership

| Path | Owner |
|---|---|
| `backend/app/models`, `backend/alembic` (only A writes migrations, one head) | A |
| `backend/app/ingest`, `reconcile`, `sending`, `auth`, `middleware`, `config.py` | A |
| `backend/app/routers/`: `health`, `batches`, `reconcile`, `scheduler`, `auth` | A |
| `deploy/`, `docker-compose.prod.yml` | A |
| `backend/app/email_builder`, `history`, `reports` | B |
| `backend/app/routers/`: `email_queue`, `email_history`, `exceptions`, `review`, `reports`, `vendors`, `settings` | B |
| `frontend/` | B |
| `backend/app/main.py`, `backend/app/contract.py`, `backend/app/routers/__init__.py`, this file, `test_contract.py` | Shared, frozen |

Each person writes tests for their own code under `backend/tests/`.

## 2. Conventions

- **Money** is `Decimal` in Python, `Numeric(14,2)` in the DB, and a **string** in JSON (`"545060.00"`). Never float.
- Dates are ISO `YYYY-MM-DD`; datetimes are ISO 8601. Business timezone is `Asia/Kolkata` (`config.TIMEZONE`).
- Enum values are the lowercase strings in `app/contract.py` (`TxnStatus`, `ExceptionCode`, `Outcome`).
- Errors use FastAPI's default `{"detail": ...}` with a proper 4xx/5xx status.
- All endpoints live under `/api`. Everything except `GET /api/health` and `POST /api/auth/login` requires auth, using a session cookie. The frontend sends `credentials: "include"`.
- Dev: the frontend's Vite dev server proxies `/api` to `http://localhost:8000`, so no CORS setup is needed.
- A stub endpoint returns header `X-Stub: true` with an example of the real shape. The owner removes the header when making the endpoint real.
- A stub function is marked `# STUB(contract)` and raises `NotImplementedError`. Don't build on its body. Only its owner edits it.

## 3. Tables (`backend/app/models/__init__.py`)

| Table | Columns | Notes |
|---|---|---|
| `batches` | id, created_at, status, source_files (JSON), error | status: `uploaded` \| `reconciled` \| `failed` |
| `vendors` | id, name, name_key (unique), email | email is a comma-separated list. `name_key` is the normalised match key; the name repeats in the source file, so it is deduped |
| `transactions` | id, batch_id, **utr (unique)**, vendor_name, vendor_id, invoice_no, po_no, grn_no, invoice_amount, cheque_amount, debit_note, diff, transaction_date, payment_date, amount_paid, tds_amount, invoice_deduction, reason, due_date, status, exception_code, status_detail | One row per consolidated-report row (1 UTR = 1 invoice; checked against the Aug–Sep data). `payment_date` = bank value date, `amount_paid` = bank debit, `due_date` = payment_date + 2. `tds_amount` / `invoice_deduction` / `reason` are NULL when they don't apply. `utr` is NULL only for `utr_missing` |
| `email_attempts` | id, created_at, outcome, vendor_id, vendor_name, to_email, due_date, subject, body_html, error, exception_code | One row per attempt, sent or not. outcome: `Outcome` |
| `email_attempt_items` | id, attempt_id, transaction_id, utr | The transactions covered by an attempt |
| `sent_utrs` | **utr (PK)**, attempt_id, sent_at | A row = that UTR was emailed. The PK is the never-twice guarantee. Only A's sending code writes it |
| `settings` | key (PK), value | Known keys: `dry_run` (`"true"`/`"false"`), `send_time` (`"HH:MM"` IST). B's router writes, A's scheduler reads |
| `users` | id, username (unique), password_hash | Managed by A's auth |

Transaction status flow: `pending` → `ready` | `exception` | `manual_review` → (`manual_review` → `ready` via `resolve_review`) → `emailed`.

## 4. Functions across the boundary (`backend/app/contract.py` holds the types)

**B provides, A calls:**

```python
# app/email_builder
def build_email(vendor_name: str, due_date: date, rows: list[EmailRow]) -> tuple[str, str]
    # -> (subject, html_body). Columns in this order: Invoice No | Invoice Amount | UTR | Payment Date |
    #    Amount Paid | TDS Amount | Invoice Deduction | Reason. A None value renders as an empty cell.

# app/history
def record_attempt(db: Session, record: AttemptRecord) -> int
    # Inserts email_attempts + email_attempt_items, COMMITS, then appends one row per UTR to the
    # append-only Excel at config.HISTORY_XLSX_PATH. Returns the attempt id.
    # Called for every attempt: sent, failed, dry_run, exception, manual_review.
```

**A provides, B calls:**

```python
# app/reconcile
def resolve_review(db: Session, transaction_id: int, reason: str) -> None
    # manual_review -> ready with the given reason. Commits. ValueError if not in manual_review.

# app/sending
def due_groups(db: Session, on: date) -> list[VendorGroup]
    # Ready transactions with due_date <= on and not in sent_utrs, grouped one per vendor + due_date.
```

## 5. Config names (`backend/app/config.py`, owned by A, read by B)

`DATABASE_URL`, `HISTORY_XLSX_PATH`, `SECRET_KEY`, `TIMEZONE`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. All are set from environment variables with dev defaults.

## 6. Endpoints

A's endpoint shapes are fixed here because B's frontend consumes them. For B's endpoints only the paths are fixed; B owns both ends, so B defines their shapes.

| Method | Path | Owner | Request → Response |
|---|---|---|---|
| GET | `/api/health` | A | → `{"status":"ok"}` (no auth) |
| POST | `/api/auth/login` | A | `{username, password}` → `{username}` + session cookie (no auth) |
| POST | `/api/auth/logout` | A | → 204 |
| GET | `/api/auth/me` | A | → `{username}` or 401 |
| POST | `/api/batches` | A | multipart files `consolidated`, `bank`, `gdn`, `tds`, `vendors` → 201 `Batch` |
| GET | `/api/batches` | A | → `[Batch]`, newest first |
| GET | `/api/batches/{batch_id}` | A | → `Batch` + `counts: {pending, ready, exception, manual_review, emailed}` |
| POST | `/api/reconcile/{batch_id}` | A | → `{batch_id, ready, exception, manual_review, skipped_duplicate}` |
| GET | `/api/scheduler` | A | → `{next_run_at, last_run_at, dry_run: bool}` |
| POST | `/api/scheduler/run?on=YYYY-MM-DD` | A | Runs the T+2 send now → `{on, sent, failed, dry_run, skipped}` |
| GET | `/api/email-queue?on=` | B | |
| GET | `/api/email-history` | B | |
| GET | `/api/email-history/export` | B | |
| GET | `/api/exceptions` | B | |
| GET | `/api/review` | B | |
| POST | `/api/review/{transaction_id}` | B | `{reason}`; calls `resolve_review` |
| GET | `/api/reports/summary` | B | |
| GET | `/api/vendors` | B | |
| GET / PUT | `/api/settings` | B | |

`Batch` = `{id, created_at, status, source_files: {consolidated, bank, gdn, tds, vendors}, error}`

## 7. Input files (as seen in the Aug–Sep 2026 reference files)

| Upload field | Real file | Key columns |
|---|---|---|
| `consolidated` | Consolidated Pharmacy *.xlsx | `benefName` (vendor), `Narration 2- Invoice No`, `Narration 3- PO No`, `GRN NO:`, `Invoice Amount`, `Cheque Amount`, `Debit Note`, `Diff`, `Transaction Date`, `UTR NO:` |
| `bank` | Bank statement *.xls (legacy xls) | `Value Date` (dd/mm/yyyy), `Ref / Cheque No` (UTR), `Debit` (Indian format `5,45,060.00`), `Description`. Refs repeat on the credit side, so match debits only |
| `gdn` | Credit note Consolidated *.xlsx (one sheet per month plus `TOTAL`) | `Particulars` (vendor), `Voucher Ref. No.` (vendor invoice), `Narration` (reason), `Gross Total` |
| `tds` | 194Q TDS *.xlsx | `PARTY NAME`, `Inv No`, `TDS` / `Total TDS` |
| `vendors` | Vendor Contact list *.xlsx (sheets `Vendor`, `CFA`) | `Vendor\nName`, `Email ID` (may hold several, `;`-separated) |
