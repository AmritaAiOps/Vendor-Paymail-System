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
| `.env.example`, `backend/requirements.txt` | Each person edits only their own `# --- A ---` / `# --- B ---` block |
| `backend/app/main.py`, `backend/app/contract.py`, `backend/app/routers/__init__.py`, this file, `test_contract.py` | Shared, frozen |

Each person writes tests for their own code under `backend/tests/`.

## 2. Conventions

- **Money** is `Decimal` in Python, `NUMERIC(14,2)` in the DB, and a **string** in JSON (`"545060.00"`). Never float.
- Dates are ISO `YYYY-MM-DD`; datetimes are ISO 8601. Business timezone is `Asia/Kolkata` (`config.TIMEZONE`).
- Enum values are the UPPERCASE strings in `app/contract.py`. In the DB they are VARCHAR with a CHECK constraint, not native PG enums.
- Errors use FastAPI's default `{"detail": ...}` with a proper 4xx/5xx status.
- All endpoints live under `/api`. Everything except `GET /api/health` and `POST /api/auth/login` requires auth, using a session cookie. The frontend sends `credentials: "include"`.
- Dev: the frontend's Vite dev server proxies `/api` to `http://localhost:8000`, so no CORS setup is needed.
- A stub endpoint returns header `X-Stub: true` with an example of the real shape. The owner removes the header when making the endpoint real.
- A stub function is marked `# STUB(contract)` and raises `NotImplementedError`. Don't build on its body. Only its owner edits it.

## 3. Tables (`backend/app/models/__init__.py`)

Money columns marked $ are NUMERIC(14,2).

| Table | Columns | Notes |
|---|---|---|
| `upload_batches` | id, uploaded_at, uploaded_by, consolidated_file, bank_file, gdn_file, tds_file, vendors_file, status, error_message | status `BatchStatus`: UPLOADED \| RECONCILED \| FAILED |
| `consolidated_entries` | id, batch_id, vendor_name, utr, invoice_no, po_no, grn_no, invoice_amount$, cheque_amount$, debit_note$, diff$, transaction_date | utr is NULL on rows with no UTR |
| `bank_transactions` | id, batch_id, value_date, utr, debit$, description, vendor_name, ifsc | Debit side only. vendor_name and ifsc are parsed from description |
| `gdn_records` | id, batch_id, vendor_name, invoice_no, voucher_no, gdn_date, amount$, reason | invoice_no = vendor invoice (`Voucher Ref. No.`), reason = `Narration` |
| `tds_records` | id, batch_id, vendor_name, invoice_no, invoice_date, tds_amount$ | |
| `vendors` | id, party_name (unique), email, is_email_valid | email is a comma-separated list |
| `reconciliation_results` | id, consolidated_entry_id (unique), bank_txn_id, invoice_value$, payment_date, amount_paid$, tds_amount$, invoice_deduction$, reason, status, exception_type | status `ResultStatus`: PAID_IN_FULL \| TDS_ONLY \| DEDUCTION \| EXCEPTION \| MANUAL_REVIEW. exception_type `ExceptionType`. NULL = cell doesn't apply |
| `email_queue` | id, vendor_id, send_on_date, status, sent_at, subject, body_html | One row per vendor + send_on_date. status `QueueStatus`: PENDING \| SENT \| FAILED \| SKIPPED |
| `email_items` | id, email_queue_id, reconciliation_result_id, **utr (unique)** | The UNIQUE on utr is the never-emailed-twice guarantee |
| `send_logs` | id, email_queue_id, timestamp, status, error_message | status `HistoryStatus` |
| `audit_log` | id, who, what, logged_at, old_value, new_value | |
| `email_history` | id, logged_at, batch_id, vendor_name, to_email, subject, invoice_no, utr, invoice_amount$, payment_date, amount_paid$, tds_amount$, invoice_deduction$, reason, status, not_sent_reason, scheduled_send_date, sent_at, error_message, email_queue_id | One row per invoice per outcome. **Append-only: DB triggers reject UPDATE and DELETE.** status `HistoryStatus`: SENT \| FAILED \| DRY_RUN \| NOT_SENT. not_sent_reason `ExceptionType` |
| `app_settings` | key (PK), value, updated_by, updated_at | Read and written **only** through `config.get_setting` / `config.set_setting`. Known keys: `dry_run` (`"true"`/`"false"`), `send_time` (`"HH:MM"` IST) |

`ExceptionType`: UTR_NOT_FOUND \| VENDOR_NOT_FOUND \| INVALID_EMAIL \| REASON_MISSING. REASON_MISSING goes with status MANUAL_REVIEW.

## 4. Functions across the boundary (`backend/app/contract.py` holds the types)

**B provides, A calls:**

```python
# app/email_builder
def build_email(vendor_name: str, due_date: date, rows: list[EmailRow]) -> tuple[str, str]
    # -> (subject, html_body). Columns in this order: Invoice No | Invoice Amount | UTR | Payment Date |
    #    Amount Paid | TDS Amount | Invoice Deduction | Reason. A None value renders as an empty cell.

# app/history
def record_attempt(db: Session, record: AttemptRecord) -> None
    # Inserts one email_history row per record.rows entry, COMMITS, then appends the same rows to the
    # append-only Excel at config.HISTORY_XLSX_PATH. Called for every attempt: SENT, FAILED, DRY_RUN, NOT_SENT.
```

**A provides, B calls:**

```python
# app/reconcile
def resolve_review(db: Session, result_id: int, reason: str, who: str) -> None
    # MANUAL_REVIEW -> DEDUCTION with the given reason, writes audit_log, commits.
    # ValueError if the result is not MANUAL_REVIEW.

# app/config
def get_setting(db: Session, key: str, default: str | None = None) -> str | None
def set_setting(db: Session, key: str, value: str, updated_by: str) -> None   # upsert + audit_log + commit
```

## 5. Config names (`backend/app/config.py`, owned by A, read by B)

`DATABASE_URL`, `HISTORY_XLSX_PATH`, `SECRET_KEY`, `TIMEZONE`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. All are set from environment variables (see `.env.example`) with dev defaults.

## 6. Endpoints

A's endpoint shapes are fixed here because B's frontend consumes them. For B's endpoints only the paths are fixed; B owns both ends, so B defines their shapes.

| Method | Path | Owner | Request → Response |
|---|---|---|---|
| GET | `/api/health` | A | → `{"status":"ok"}`; 500 if the DB is down (no auth) |
| POST | `/api/auth/login` | A | `{username, password}` → `{username}` + session cookie (no auth) |
| POST | `/api/auth/logout` | A | → 204 |
| GET | `/api/auth/me` | A | → `{username}` or 401 |
| POST | `/api/batches` | A | multipart files `consolidated`, `bank`, `gdn`, `tds`, `vendors` → 201 `Batch` |
| GET | `/api/batches` | A | → `[Batch]`, newest first |
| GET | `/api/batches/{batch_id}` | A | → `Batch` + `counts` |
| POST | `/api/reconcile/{batch_id}` | A | → `{batch_id, counts}` |
| GET | `/api/scheduler` | A | → `{next_run_at, last_run_at, dry_run: bool}` |
| POST | `/api/scheduler/run?on=YYYY-MM-DD` | A | Runs the T+2 send now → `{on, sent, failed, dry_run, skipped}` |
| GET | `/api/email-queue?on=` | B | |
| GET | `/api/email-history` | B | |
| GET | `/api/email-history/export` | B | |
| GET | `/api/exceptions` | B | |
| GET | `/api/review` | B | |
| POST | `/api/review/{result_id}` | B | `{reason}`; calls `resolve_review` |
| GET | `/api/reports/summary` | B | |
| GET | `/api/vendors` | B | |
| GET / PUT | `/api/settings` | B | Goes through `get_setting` / `set_setting` |

`Batch` = `{id, uploaded_at, uploaded_by, consolidated_file, bank_file, gdn_file, tds_file, vendors_file, status, error_message}`
`counts` = `{PAID_IN_FULL, TDS_ONLY, DEDUCTION, EXCEPTION, MANUAL_REVIEW}` (integers)

## 7. Input files (as seen in the Aug–Sep 2026 reference files)

| Upload field | Real file | Key columns |
|---|---|---|
| `consolidated` | Consolidated Pharmacy *.xlsx | `benefName` (vendor), `Narration 2- Invoice No`, `Narration 3- PO No`, `GRN NO:`, `Invoice Amount`, `Cheque Amount`, `Debit Note`, `Diff`, `Transaction Date`, `UTR NO:` |
| `bank` | Bank statement *.xls (legacy xls), or the DLB statement (same layout, debit-only, password-protected) | `Value Date` (dd/mm/yyyy), `Ref / Cheque No` (UTR), `Debit` (Indian format `5,45,060.00`), `Description` |
| `gdn` | Credit note Consolidated *.xlsx (one sheet per month plus `TOTAL`) | `Particulars` (vendor), `Voucher Ref. No.` (vendor invoice), `Narration` (reason), `Gross Total` |
| `tds` | 194Q TDS *.xlsx | `PARTY NAME`, `Inv No`, `TDS` / `Total TDS` |
| `vendors` | Vendor Contact list *.xlsx (sheets `Vendor`, `CFA`) | `Vendor\nName`, `Email ID` (may hold several, `;`-separated) |
