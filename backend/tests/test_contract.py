"""Fails if anything in docs/CONTRACT.md drifts. Run before calling any phase done."""
import inspect

from sqlalchemy import Numeric

from app import email_builder, history, reconcile, sending
from app.main import app
from app.models import Base

TABLES = {
    "batches": {"id", "created_at", "status", "source_files", "error"},
    "vendors": {"id", "name", "name_key", "email"},
    "transactions": {
        "id", "batch_id", "utr", "vendor_name", "vendor_id", "invoice_no", "po_no", "grn_no",
        "invoice_amount", "cheque_amount", "debit_note", "diff", "transaction_date", "payment_date",
        "amount_paid", "tds_amount", "invoice_deduction", "reason", "due_date", "status",
        "exception_code", "status_detail",
    },
    "email_attempts": {
        "id", "created_at", "outcome", "vendor_id", "vendor_name", "to_email", "due_date",
        "subject", "body_html", "error", "exception_code",
    },
    "email_attempt_items": {"id", "attempt_id", "transaction_id", "utr"},
    "sent_utrs": {"utr", "attempt_id", "sent_at"},
    "settings": {"key", "value"},
    "users": {"id", "username", "password_hash"},
}

MONEY = {"invoice_amount", "cheque_amount", "debit_note", "diff", "amount_paid", "tds_amount", "invoice_deduction"}

FUNCTIONS = {
    email_builder.build_email: "(vendor_name: str, due_date: datetime.date, rows: list[app.contract.EmailRow]) -> tuple[str, str]",
    history.record_attempt: "(db: sqlalchemy.orm.session.Session, record: app.contract.AttemptRecord) -> int",
    reconcile.resolve_review: "(db: sqlalchemy.orm.session.Session, transaction_id: int, reason: str) -> None",
    sending.due_groups: "(db: sqlalchemy.orm.session.Session, on: datetime.date) -> list[app.contract.VendorGroup]",
}

ROUTES = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/me"),
    ("POST", "/api/batches"), ("GET", "/api/batches"), ("GET", "/api/batches/{batch_id}"),
    ("POST", "/api/reconcile/{batch_id}"),
    ("GET", "/api/scheduler"), ("POST", "/api/scheduler/run"),
    ("GET", "/api/email-queue"),
    ("GET", "/api/email-history"), ("GET", "/api/email-history/export"),
    ("GET", "/api/exceptions"),
    ("GET", "/api/review"), ("POST", "/api/review/{transaction_id}"),
    ("GET", "/api/reports/summary"),
    ("GET", "/api/vendors"),
    ("GET", "/api/settings"), ("PUT", "/api/settings"),
}


def test_tables_and_columns():
    for name, cols in TABLES.items():
        assert name in Base.metadata.tables, name
        assert cols <= set(Base.metadata.tables[name].c.keys()), (name, cols - set(Base.metadata.tables[name].c.keys()))


def test_money_is_numeric():
    t = Base.metadata.tables["transactions"]
    for c in MONEY:
        assert isinstance(t.c[c].type, Numeric) and t.c[c].type.asdecimal, c


def test_utr_unique_and_sent_utr_pk():
    assert Base.metadata.tables["transactions"].c.utr.unique
    assert Base.metadata.tables["sent_utrs"].c.utr.primary_key


def test_function_signatures():
    for fn, sig in FUNCTIONS.items():
        got = str(inspect.signature(fn)).replace("<class '", "").replace("'>", "")
        assert got == sig, f"{fn.__module__}.{fn.__name__}: {got}"


def test_routes():
    have = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert ROUTES <= have, ROUTES - have
