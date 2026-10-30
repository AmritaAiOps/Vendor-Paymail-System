import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_setting, set_setting
from app.models import AuditLog, EmailHistory, EmailItem, ReconciliationResult
from scripts.seed_fixture import seed


def test_duplicate_utr_rejected(db):
    db.add(EmailItem(email_queue_id=1, reconciliation_result_id=1, utr="DLXBH00018402789"))
    db.commit()
    db.add(EmailItem(email_queue_id=2, reconciliation_result_id=2, utr="DLXBH00018402789"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_bounced_is_an_allowed_exception_type(db):
    db.add(ReconciliationResult(consolidated_entry_id=1, invoice_value=1, status="EXCEPTION", exception_type="BOUNCED"))
    db.add(EmailHistory(vendor_name="X", status="NOT_SENT", not_sent_reason="BOUNCED"))
    db.commit()
    with pytest.raises(IntegrityError, match="CHECK"):
        db.execute(text("INSERT INTO email_history (vendor_name, status, not_sent_reason) VALUES ('X', 'NOT_SENT', 'NOPE')"))


def test_email_history_is_append_only(db):
    db.add(EmailHistory(vendor_name="KOMAL AGENCIES", status="SENT"))
    db.commit()
    for sql in ("UPDATE email_history SET status = 'FAILED'", "DELETE FROM email_history"):
        with pytest.raises(IntegrityError, match="append-only"):
            db.execute(text(sql))
        db.rollback()


def test_settings_env_first_then_table_then_default(db, monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    assert get_setting("dry_run") == "true"  # default
    set_setting("dry_run", "false")
    assert get_setting("dry_run") == "false"  # table
    monkeypatch.setenv("DRY_RUN", "true")
    assert get_setting("dry_run") == "true"  # env wins
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert (last.what, last.old_value, last.new_value) == ("setting:dry_run", None, "false")
    with pytest.raises(KeyError):
        get_setting("smtp_password")  # secrets can't be read through the settings store


def test_seed_fixture_loads_three_results_once(db):
    seed(db)
    assert {r.status for r in db.query(ReconciliationResult)} == {"PAID_IN_FULL", "TDS_ONLY", "DEDUCTION"}
    with pytest.raises(ValueError, match="already seeded"):
        seed(db)
