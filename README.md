# Vendor Payment Reconciliation: Email Automation

Internal tool for Sudhamayi Enterprises Pvt. Ltd. It matches each Consolidated Report payment to the bank statement by UTR, works out the TDS and invoice deduction (reason from the GDN Report), and emails every vendor a table of their payments on T+2. Every attempt, sent or not, is kept in the database, in an append-only Excel file and on the Email History page.

The interface between the two tracks is in [docs/CONTRACT.md](docs/CONTRACT.md).

Layout: `backend/` (FastAPI, Person A + B), `frontend/` (React + Vite, Person B), `deploy/` (Nginx and the frontend image, Person A).
`.env.example` and `backend/requirements.txt` have `# --- A ---` / `# --- B ---` blocks. Edit only your own block.

> **No login yet.** Anyone who can reach the app can use it, including sending emails. Run it only on the trusted internal network until Firebase login lands.

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

## Docker (dev: app + Postgres)

```
cp .env.example .env   # set POSTGRES_PASSWORD
docker compose up --build
```

## Production

One host with Docker. `docker-compose.prod.yml` runs three containers:

| Service | What | Published |
|---|---|---|
| `web` | Nginx: the built frontend, `/api` proxied to `app`, upload size cap and rate limit, security headers | `HTTP_PORT` (80) |
| `app` | FastAPI + the daily send job. Runs `alembic upgrade head` on every start | no |
| `db` | PostgreSQL 16, data in volume `pgdata` | no |

The email history Excel file lives in volume `appdata` (`/app/data/email_history.xlsx` in `app`).

```
cp .env.example .env        # fill in: see the table below
docker compose -f docker-compose.prod.yml up -d --build
sh deploy/smoke.sh          # health, routes, headers, 413 body cap, 429 upload rate limit
```

Run exactly **one** `app` container: the send job runs inside it. Two would both run it; the queue claim stops double sends, but there is no reason for it.

### Environment variables

Secrets come only from the environment (`.env`, never committed). The settings page can change only `dry_run`, `send_time` and `signature`; an env var of the same name wins over it.

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | none (required in prod) | Letters and digits only: it goes into the database URL unescaped |
| `DATABASE_URL` | `sqlite:///./dev.db` | Set by `docker-compose.prod.yml`; leave it alone there |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | empty, `587` | The company mail server |
| `SMTP_FROM`, `SMTP_FROM_NAME` | empty, company name | Sender address and display name |
| `SMTP_STARTTLS` | `true` | |
| `DRY_RUN` | `true` | Emails are rendered and logged but **not sent** unless this is `false` (or unset and the setting is off) |
| `TEST_RECIPIENT` | empty | Sends every email to this one inbox. Empty in production |
| `SEND_TIME` | `10:00` | Daily send time, IST. Overrides the setting; restart after changing |
| `SIGNATURE` | `[Name, designation]` | Sign-off under the email table. Overrides the setting |
| `MAX_UPLOAD_MB` | `20` | Per uploaded file. Also change `client_max_body_size` in `deploy/nginx.conf` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HTTP_PORT` | `80` | Port Nginx publishes |
| `HISTORY_XLSX_PATH` | `./data/email_history.xlsx` | Set by `docker-compose.prod.yml` to the `appdata` volume |

## Operations runbook

All commands from the repo root; `dc` means `docker compose -f docker-compose.prod.yml`.

**Start, stop, status.** `dc up -d` · `dc down` (keeps the volumes; never add `-v`) · `dc ps`.

**Logs.** `dc logs -f app` (JSON lines: `level`, `logger`, `message`, `request_id`) and `dc logs -f web` (one JSON line per request). A failed request answers `Internal server error (ref <id>)`; search both logs for that id. Logs rotate at 10 MB × 5 files per container.

**Upgrade.** `git pull`, then `dc up -d --build`. Database migrations run automatically when `app` starts; if one fails, `app` keeps restarting and `dc logs app` shows why. Take a backup first.

**Going live with email.** Check SMTP with `DRY_RUN=true` first (history shows `DRY_RUN` rows), then set `DRY_RUN=false` and `dc up -d`. To test against one inbox, set `TEST_RECIPIENT`.

**Daily send.** Runs at `send_time` IST. `curl -X POST http://<host>/api/scheduler/run-now` runs it immediately. It answers 503 if real sending is on but SMTP isn't configured, and touches nothing.

**A queue row stuck in `SENDING`.** The app died mid-send; the email may or may not have gone out. It is never resent automatically. Check the mailbox's Sent folder, then fix the row by hand in the database (`SENT` with `sent_at`, or back to `PENDING` to resend).

**Emails not going out.** In order: `DRY_RUN` still on? SMTP variables set? `dc logs app | grep email_queue` for `FAILED` / `skipped` lines. Exceptions and Manual Review pages list invoices that will never be emailed until fixed.

**Upload refused.** 413 = a request over the Nginx cap; 429 = more than 10 uploads a minute from one address, wait a minute; 422 = the reply lists each file's problem (wrong type, too big, password-protected, missing columns).

**History Excel file missing or damaged.** The database is the source of truth: `curl -X POST http://<host>/api/email-history/rebuild-xlsx` rewrites it from the `email_history` table.

### Backups

Two things hold data: the Postgres database (everything, including the full email history) and the history Excel file in volume `appdata`. The Excel file can always be rebuilt from the database, but back it up too so it can be restored exactly as the team last saw it.

Daily, on the host (for example from cron), keeping at least 30 days, and copied off the machine:

```
dc exec -T db pg_dump -U paymail -Fc paymail > backup/paymail-$(date +%F).dump
dc cp app:/app/data/email_history.xlsx backup/email_history-$(date +%F).xlsx
```

Restore:

```
dc stop app
dc exec -T db pg_restore -U paymail -d paymail --clean --if-exists < backup/paymail-YYYY-MM-DD.dump
dc cp backup/email_history-YYYY-MM-DD.xlsx app:/app/data/email_history.xlsx
dc start app
dc exec -u root app chown app:app /app/data/email_history.xlsx   # docker cp leaves it owned by root, read-only to the app
```

`email_history` is append-only (database triggers reject UPDATE and DELETE). `pg_restore --clean` drops and recreates the table, which is allowed; nothing else should touch it. Test a restore on a spare machine once before you rely on it.

## Contributing

Two people build in parallel. Person A owns the engine and Person B owns delivery; [docs/CONTRACT.md](docs/CONTRACT.md) says who owns what, and [.github/CODEOWNERS](.github/CODEOWNERS) mirrors it.

- Both people branch from the tag `foundation-v1`. Person A works on `backend`; Person B works on their own branch.
- Commit at the end of every phase, on your own branch.
- Nothing goes to `main` until the final merge.
- Never edit a folder you don't own. Shared files (contract, schemas, `main.py`, fixture, contract test) change only when both people agree.
- Only Person A writes Alembic migrations.
- Before finishing any phase, and again after the merge, run `.venv/Scripts/python -m pytest tests/contract -q` from `backend/`.
