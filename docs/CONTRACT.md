# Contract: Person A (Engine) ↔ Person B (Delivery)

Frozen at tag `foundation-v1`. Any change: stop, write it up, both people agree, then update this file, `backend/app/schemas.py` / `contract.py` and the stubs in the same commit. Nobody changes it silently.

The Pydantic models in `backend/app/schemas.py` are this contract in code. `backend/tests/contract/test_contract.py` reads the endpoint table (b) and the function table (c) **from this file** and checks them against the running app. Both people run it before finishing any phase and again after the merge:

```
cd backend && .venv/Scripts/python -m pytest tests/contract -q
```

## Folder ownership

| Path | Owner |
|---|---|
| `backend/app/models`, `backend/alembic` (only A writes migrations, one head) | A |
| `backend/app/ingest`, `reconcile`, `sending`, `middleware`, `config.py`, `backend/scripts` | A |
| `backend/app/routers/`: `health`, `batches`, `scheduler` | A |
| `deploy/`, `docker-compose.prod.yml` | A |
| `backend/app/email_builder`, `history`, `reports` | B |
| `backend/app/routers/`: `reports`, `email_queue`, `email_history`, `exceptions`, `manual_review`, `vendors`, `settings` | B |
| `frontend/` | B |
| `.env.example`, `backend/requirements.txt` | Each person edits only their own `# --- A ---` / `# --- B ---` block |
| `backend/app/main.py`, `contract.py`, `schemas.py`, `routers/__init__.py`, `backend/tests/contract/`, `backend/tests/fixtures/`, this file | Shared, frozen |

`.github/CODEOWNERS` mirrors this table.

## Conventions

- **Money** is `Decimal` in Python, `NUMERIC(14,2)` in the DB, and a **string** in JSON (`"545060.00"`). Never float.
- Dates are ISO `YYYY-MM-DD`; datetimes are ISO 8601. Business timezone is `Asia/Kolkata` (`config.TIMEZONE`).
- Enum values are the UPPERCASE strings in `app/contract.py`. In the DB they are VARCHAR with a CHECK constraint.
- In API responses, NULL means the cell doesn't apply. The email renders it as an empty cell, never as "0", "n/a" or "No deduction".
- Errors use FastAPI's default `{"detail": ...}` with a proper 4xx/5xx status.
- **No login.** There are no users or roles; every endpoint is open to anyone who can reach the app. Run it only on a trusted internal network.
- Stubs: a stub route has `STUB` (from `app/routers/__init__.py`) in its dependencies and answers with header `X-Stub: true` and canned data from the fixture. The owner removes `STUB` when the route becomes real. A stub function is marked `# STUB(contract)`. Don't build on its body. Only its owner edits it.
- Dev: the frontend's Vite dev server proxies `/api` to `http://localhost:8000`.
- Foreign keys are enforced on SQLite too (dev and tests), exactly like Postgres: a test that inserts a row must first create the rows it points at (`scripts.seed_fixture.seed` gives a vendor, a batch and three results).

## (a) Tables: who writes, who reads

| Table | Writes | Reads |
|---|---|---|
| `upload_batches`, `consolidated_entries`, `bank_transactions`, `gdn_records`, `tds_records`, `reconciliation_results`, `send_logs` | A | B |
| `vendors` | A creates rows on upload. B writes only `email` and `is_email_valid` (the email fix) | A, B |
| `email_queue`, `email_items` | B creates rows (`build_queue`), status `PENDING`, `send_on_date` from `sending.send_on_date`. A updates only `email_queue.status`, `sent_at`, and on SENT the `subject` / `body_html` actually sent | A, B |
| `email_history` | A only, through `sending.record_history`. Append-only: DB triggers reject UPDATE and DELETE | B reads and exports |
| `audit_log` | A and B, append only | A, B |
| `app_settings` | Only through `config.get_setting` / `config.set_setting` | Same |

`email_items.utr` is UNIQUE: that constraint is the never-emailed-twice guarantee. Columns are in `backend/app/models/__init__.py`.

Data rules the screens rely on:

- **Bounced payments.** A bank credit saying `NEFT RETURN-<reason>-<name>-<UTR>` marks the debit with that UTR `bank_transactions.is_bounced = true`, with the return text in `bounce_note`. Reconciliation gives that invoice `status = EXCEPTION`, `exception_type = BOUNCED`, and no email goes out. Its history row is `NOT_SENT` / `BOUNCED`. B shows BOUNCED rows **highlighted** wherever exceptions or history appear.
- **Vendor emails.** `vendors.email` holds every valid address from "Email ID" and "Email ID- Contact 2", comma-separated; all of them are mailed. If the main Email ID cell doesn't parse cleanly, the original text is kept with `is_email_valid = false` (never guessed). A bad contact-2 cell is ignored and reported.
- **Vendor names** match ignoring case, spaces, punctuation and Private/Pvt, Limited/Ltd, Company/Co, &/and (`ingest.clean.name_key`): `R.K PHARMA` = `R.K. Pharma`. If that finds nothing, a looser key that also drops (bracketed) text and company suffixes is tried, but only when it points at exactly one vendor: `PHARMAGIX` = `Pharmagix(A Unit Of White Pharmaceuticals)`, while a company and its CFA (`Aark Pharmaceuticals` / `Aark Pharmaceuticals (Neon Cfa)`) stay unmatched rather than guessed. The matched vendor is stored in `reconciliation_results.vendor_id`; `build_queue` uses that, not the name.
- **Reconciliation rule** (A's `reconcile.decide`). Exceptions first, in this order: UTR not in the bank debits → `UTR_NOT_FOUND`; bounced → `BOUNCED`; no vendor → `VENDOR_NOT_FOUND`; vendor email invalid → `INVALID_EMAIL`. Then shortfall = invoice value − bank debit, with ₹1 rounding everywhere:
  - shortfall ≤ ₹1 → `PAID_IN_FULL`
  - shortfall = TDS (TDS file) → `TDS_ONLY`
  - shortfall = TDS + GDN debit note(s), or = GDN alone (TDS listed but not cut) → `DEDUCTION`, reason = the GDN narration(s), joined with "; "
  - shortfall but no debit note → `MANUAL_REVIEW` / `REASON_MISSING` (deduction amount kept for the review page)
  - TDS > shortfall, overpaid by > ₹1, or a debit note that doesn't match the shortfall → `MANUAL_REVIEW` / `AMOUNT_MISMATCH`
  - TDS and GDN are matched on vendor + invoice no; if the vendor is spelled differently in that file, on invoice no alone, but only when that invoice no is used by one vendor in both files.
  - Payment date = bank value date (`reconcile.payment_date`, the one place to change it). Send date = `sending.send_on_date(payment_date)`.
  - Only `PAID_IN_FULL`, `TDS_ONLY` and `DEDUCTION` results are sendable.
- **Sending** (A's `sending.run_due`, daily at `send_time` Asia/Kolkata, or `POST /api/scheduler/run-now`). For every `PENDING` queue row with `send_on_date` ≤ today:
  - claim it `PENDING → SENDING` in one conditional UPDATE (two runs can never take the same row);
  - skip it (`SKIPPED`) if the vendor email is invalid, any invoice isn't sendable, or any UTR already has a `SENT` history row;
  - render it with B's `render_email`, then send it, or in DRY_RUN only log it;
  - finish in one transaction: status `SENT` / `FAILED` (or back to `PENDING` in DRY_RUN), a `send_logs` row and the `email_history` rows.
  - Only failures where nothing reached the mail server are retried (3 tries, 2 s then 4 s). `FAILED` is final. A row still `SENDING` after a run means it died mid-send: check by hand, it is never resent automatically.
  - **DRY_RUN is on unless `dry_run` is explicitly false** (env `DRY_RUN` or the setting). `TEST_RECIPIENT` (env) sends everything to one inbox, subject prefixed `[TEST for <vendor emails>]`; those still count as SENT.
- **History rows** (`email_history`): one per invoice per outcome. `SENT`, `FAILED` (with the error) and `DRY_RUN` from the sender; `NOT_SENT` with `not_sent_reason` = the result's `exception_type`, written by reconciliation for every EXCEPTION / MANUAL_REVIEW invoice. `DRY_RUN` and `NOT_SENT` are written once per UTR (per vendor + invoice without a UTR) and reason; re-runs add nothing. After every reconcile and every send run A calls B's `history.xlsx.append_new_rows`; if it fails, that is logged and nothing else changes.

## (b) Endpoints

Request and response names are models in `backend/app/schemas.py`. `xlsx` = an Excel file download.

| Method | Path | Owner | Request | Response |
|---|---|---|---|---|
| GET | /api/health | A | none | HealthOut |
| POST | /api/batches | A | multipart files: consolidated, bank, gdn, tds, vendors (.xlsx/.xls, ≤ `MAX_UPLOAD_MB` each, default 20) | 201 BatchOut; 422 `detail: [{file, message}]` listing every problem, nothing stored |
| GET | /api/batches/{id}/summary | A | none | BatchSummary |
| POST | /api/batches/{id}/reconcile | A | none | BatchSummary; re-runnable (results already queued for email are left alone); ends by calling `build_queue(session, batch_id=id)`; 404 if no batch |
| GET | /api/batches/{id}/results | A | query: status? (ResultStatus), vendor? (part of name, any case), limit (1–500, default 100), offset | list[ResultOut] in consolidated-report order; total before paging in header `X-Total-Count`; 404 if no batch |
| POST | /api/scheduler/run-now | A | none | RunNowOut (counts of this run); 503 if real sending is on but SMTP isn't configured, nothing touched. No admin check: there is no login |
| GET | /api/batches/{id}/proforma.xlsx | B | none | xlsx |
| GET | /api/batches/{id}/report.xlsx | B | none | xlsx |
| GET | /api/email-queue | B | query: batch_id?, status? (QueueStatus) | list[QueueItemOut] |
| GET | /api/email-queue/{id}/preview | B | none | EmailPreview |
| GET | /api/email-history | B | query: date_from?, date_to? (YYYY-MM-DD, on `logged_at`), vendor? (part of name, any case), status? (HistoryStatus), q? (text search), limit (default 50), offset | list[HistoryOut]; total before paging in header `X-Total-Count`; counts per status as a JSON object in header `X-Status-Counts` |
| GET | /api/email-history/{id} | B | none | HistoryOut |
| GET | /api/email-history/export.xlsx | B | none | xlsx |
| POST | /api/email-history/rebuild-xlsx | B | none | RowCountOut |
| GET | /api/exceptions | B | none | list[ResultOut] |
| GET | /api/exceptions/export.xlsx | B | none | xlsx |
| GET | /api/manual-review | B | none | list[ResultOut] |
| PUT | /api/manual-review/{result_id}/reason | B | ReasonIn | ResultOut |
| POST | /api/manual-review/gdn-upload | B | multipart file: file | GdnUploadOut |
| PUT | /api/vendors/{id}/email | B | VendorEmailIn | VendorOut |
| GET | /api/settings | B | none | SettingsModel |
| PUT | /api/settings | B | SettingsModel | SettingsModel |

Model fields, in short (exact types are in `schemas.py`):

- `HealthOut` {status}
- `BatchOut` {id, uploaded_at, consolidated_file, bank_file, gdn_file, tds_file, vendors_file, status, error_message}
- `BatchSummary` {batch: BatchOut, counts: {ResultStatus: int}, with every status present, files: {consolidated|bank|gdn|tds|vendors: FileReport}}
- `FileReport` {file_name, rows_read, rows_kept, rows_skipped, rows_rejected, issues: [RowIssue]}. Skipped = dropped on purpose (bank credits, totals rows, duplicate vendors)
- `RowIssue` {sheet, row (Excel row number), message, rejected: bool}. rejected=false means the row was kept but flagged, e.g. a vendor email that needs checking
- `ResultOut` {id, batch_id, vendor_name, invoice_no, utr, invoice_value, payment_date, amount_paid, tds_amount, invoice_deduction, reason, status, exception_type, send_on_date}. send_on_date = the queued email's `email_queue.send_on_date`, null if not queued
- `RunNowOut` {sent, failed, dry_run, not_sent}
- `QueueItemOut` {id, vendor_id, vendor_name, to_email, send_on_date, status, sent_at, subject, invoice_count}
- `EmailPreview` {subject, html, text}
- `HistoryOut` = every `email_history` column
- `RowCountOut` {rows} · `ReasonIn` {reason: 1–500 chars} · `GdnUploadOut` {rows_read, requeued}
- `VendorEmailIn` {email: one address or comma-separated list} · `VendorOut` {id, party_name, email, is_email_valid}
- `SettingsModel` {dry_run: bool, send_time: "HH:MM" IST, signature: ≤ 500 chars}

## (c) Shared Python functions

The signature column is checked by the contract test. Module prefixes are dropped (`Session` = `sqlalchemy.orm.Session`).

| Module | Name | Signature | Owner | Caller |
|---|---|---|---|---|
| app.config | get_setting | `(name: str) -> str` | A | A, B |
| app.config | set_setting | `(name: str, value: str) -> None` | A | B (settings page) |
| app.ingest | load_gdn_file | `(file: BinaryIO) -> list[GdnRow]` | A | B (gdn-upload) |
| app.reconcile | requeue_after_reason | `(session: Session, result_id: int, reason: str) -> None` | A | B (manual review) |
| app.reconcile | requeue_vendor_exceptions | `(session: Session, vendor_id: int) -> int` | A | B (vendor email fix) |
| app.sending | send_on_date | `(payment_date: date) -> date` | A | B (`build_queue`), A (scheduler) |
| app.email_builder | build_queue | `(session: Session, batch_id: int \| None = None, result_ids: list[int] \| None = None) -> list[int]` | B | A (after reconcile and requeue) |
| app.email_builder | render_email | `(session: Session, queue_id: int) -> tuple[str, str, str]` | B | A (sender), B (preview) |
| app.history.xlsx | append_new_rows | `(session: Session) -> int` | B | A (after each history write) |
| app.history.xlsx | rebuild | `(session: Session) -> int` | B | B (rebuild-xlsx) |

What each one does:

- `get_setting(name)`: env var `NAME` (upper-case) first, then the `app_settings` row, then the default. Only known names are allowed: `dry_run` (default `"true"`), `send_time` (default `"10:00"`) and `signature` (default `"[Name, designation]"`, the sign-off `render_email` puts under the table). KeyError for anything else, so secrets in the environment can't be read through it.
- `set_setting(name, value)`: upserts the `app_settings` row and appends to `audit_log` in one commit. An env var with the same name still wins on read.
- `load_gdn_file(file)`: parses a GDN Report workbook (all month sheets) into `GdnRow`s (`contract.py`). It doesn't write to the DB. ValueError if the file isn't a GDN Report.
- `requeue_after_reason(...)`: sets the reason on a MANUAL_REVIEW result, moves it to DEDUCTION, writes `audit_log`, then calls `build_queue(result_ids=[result_id])`. A send date already in the past goes out on the next run. ValueError if the result isn't MANUAL_REVIEW, has no deduction to explain (overpaid, or TDS larger than the shortfall), or the reason is empty or over 500 characters.
- `requeue_vendor_exceptions(session, vendor_id)`: re-checks that vendor's INVALID_EMAIL results and every VENDOR_NOT_FOUND result with the full rule set; those that now match this vendor are updated, and the sendable ones are queued with `build_queue(result_ids=[...])`. Returns how many were queued. ValueError if the vendor doesn't exist. Call it after fixing a vendor's email or adding a vendor.
- `send_on_date(payment_date)`: the T+2 rule, already real (not a stub). Counts 2 business days after the bank value date, where every day except Sunday is a business day; holidays are not skipped. Fri→Mon, Sat→Tue, Thu→Sat. Nobody computes a send date any other way.
- `build_queue(...)`: creates `email_queue` (one row per vendor + send date, from `send_on_date`) and `email_items` (one per UTR) for the sendable results of a batch, or for the given results. Skips UTRs already in `email_items`. Returns the new queue ids.
- `render_email(session, queue_id)`: returns `(subject, html, text)`. Called while the row is `SENDING`; it must not commit or change the queue row. If it raises, that email is marked FAILED. Table columns in this order: Invoice No | Invoice Amount | UTR | Payment Date | Amount Paid | TDS Amount | Invoice Deduction | Reason. Empty cells stay empty.
- `append_new_rows(session)`: appends `email_history` rows not yet in the Excel file at `config.HISTORY_XLSX_PATH`. `rebuild(session)` rewrites that file from the whole table. Both return a row count.

## Shared fixture and seed

- `backend/tests/fixtures/three_row_example.py`: ABC Pharma Distributors with three invoices (INV-2305 paid in full, INV-2310 TDS only, INV-2291 deduction "Goods returned (DN-0457)"). It holds source rows for all five input files, the parsed DB rows, the expected `reconciliation_results`, and the expected email cells as strings. Invented values are marked SAMPLE.
- `backend/scripts/seed_fixture.py` loads the vendor and results into the dev DB, so B can build the email and screens without the engine.

## Input files (as seen in the Aug–Sep 2026 reference files)

| Upload field | Real file | Key columns |
|---|---|---|
| `consolidated` | Consolidated Pharmacy *.xlsx | `benefName` (vendor), `Narration 2- Invoice No`, `Narration 3- PO No`, `GRN NO:`, `Invoice Amount`, `Cheque Amount`, `Debit Note`, `Diff`, `Transaction Date`, `UTR NO:` |
| `bank` | Bank statement *.xls (legacy xls), or the DLB statement (same layout, debit-only, password-protected) | `Value Date` (dd/mm/yyyy), `Ref / Cheque No` (UTR), `Debit` (Indian format `5,45,060.00`), `Description` |
| `gdn` | Credit note Consolidated *.xlsx (one sheet per month plus `TOTAL`) | `Particulars` (vendor), `Voucher Ref. No.` (vendor invoice), `Narration` (reason), `Gross Total` |
| `tds` | 194Q TDS *.xlsx | `PARTY NAME`, `Inv No`, `TDS` / `Total TDS` |
| `vendors` | Vendor Contact list *.xlsx (sheet `Vendor` = distributors/stockists, sheet `CFA` = drug companies' carrying & forwarding agents; both are read) | `Vendor Name`, `Email ID`, `Email ID- Contact 2` (each may hold several addresses separated by `;`, `,` or `/`) |
