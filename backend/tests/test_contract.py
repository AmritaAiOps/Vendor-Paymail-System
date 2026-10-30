"""Fails if anything in docs/CONTRACT.md drifts. Run before calling any phase done."""
import inspect

from sqlalchemy import Numeric

from app import config, email_builder, history, reconcile
from app.main import app
from app.models import Base

TABLES = {
    "upload_batches": {"id", "uploaded_at", "uploaded_by", "consolidated_file", "bank_file", "gdn_file", "tds_file",
                       "vendors_file", "status", "error_message"},
    "consolidated_entries": {"id", "batch_id", "vendor_name", "utr", "invoice_no", "po_no", "grn_no", "invoice_amount",
                             "cheque_amount", "debit_note", "diff", "transaction_date"},
    "bank_transactions": {"id", "batch_id", "value_date", "utr", "debit", "description", "vendor_name", "ifsc"},
    "gdn_records": {"id", "batch_id", "vendor_name", "invoice_no", "voucher_no", "gdn_date", "amount", "reason"},
    "tds_records": {"id", "batch_id", "vendor_name", "invoice_no", "invoice_date", "tds_amount"},
    "vendors": {"id", "party_name", "email", "is_email_valid"},
    "reconciliation_results": {"id", "consolidated_entry_id", "bank_txn_id", "invoice_value", "payment_date",
                               "amount_paid", "tds_amount", "invoice_deduction", "reason", "status", "exception_type"},
    "email_queue": {"id", "vendor_id", "send_on_date", "status", "sent_at", "subject", "body_html"},
    "email_items": {"id", "email_queue_id", "reconciliation_result_id", "utr"},
    "send_logs": {"id", "email_queue_id", "timestamp", "status", "error_message"},
    "audit_log": {"id", "who", "what", "logged_at", "old_value", "new_value"},
    "email_history": {"id", "logged_at", "batch_id", "vendor_name", "to_email", "subject", "invoice_no", "utr",
                      "invoice_amount", "payment_date", "amount_paid", "tds_amount", "invoice_deduction", "reason",
                      "status", "not_sent_reason", "scheduled_send_date", "sent_at", "error_message", "email_queue_id"},
    "app_settings": {"key", "value", "updated_by", "updated_at"},
}

MONEY = {"invoice_amount", "cheque_amount", "debit_note", "diff", "debit", "amount", "tds_amount", "invoice_value",
         "amount_paid", "invoice_deduction"}

FUNCTIONS = {
    email_builder.build_email: "(vendor_name: str, due_date: datetime.date, rows: list[app.contract.EmailRow]) -> tuple[str, str]",
    history.record_attempt: "(db: sqlalchemy.orm.session.Session, record: app.contract.AttemptRecord) -> None",
    reconcile.resolve_review: "(db: sqlalchemy.orm.session.Session, result_id: int, reason: str, who: str) -> None",
    config.get_setting: "(db: sqlalchemy.orm.session.Session, key: str, default: str | None = None) -> str | None",
    config.set_setting: "(db: sqlalchemy.orm.session.Session, key: str, value: str, updated_by: str) -> None",
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
    ("GET", "/api/review"), ("POST", "/api/review/{result_id}"),
    ("GET", "/api/reports/summary"),
    ("GET", "/api/vendors"),
    ("GET", "/api/settings"), ("PUT", "/api/settings"),
}


def test_tables_and_columns():
    for name, cols in TABLES.items():
        assert name in Base.metadata.tables, name
        assert cols <= set(Base.metadata.tables[name].c.keys()), (name, cols - set(Base.metadata.tables[name].c.keys()))


def test_money_is_numeric_14_2():
    cols = [c for t in Base.metadata.tables.values() for c in t.c if c.name in MONEY]
    assert len(cols) >= len(MONEY)
    for c in cols:
        assert isinstance(c.type, Numeric) and (c.type.precision, c.type.scale) == (14, 2), c


def test_email_items_utr_unique():
    assert Base.metadata.tables["email_items"].c.utr.unique


def test_function_signatures():
    for fn, sig in FUNCTIONS.items():
        got = str(inspect.signature(fn)).replace("<class '", "").replace("'>", "")
        assert got == sig, f"{fn.__module__}.{fn.__name__}: {got}"


def test_routes():
    have = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert ROUTES <= have, ROUTES - have
