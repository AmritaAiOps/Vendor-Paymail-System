"""T+2 sending, history and requeue. SMTP is a fake server; queue rows are inserted directly from the fixture."""
from datetime import date

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import config
from app.ingest import ingest_batch
from app.models import (AuditLog, ConsolidatedEntry, EmailHistory, EmailItem, EmailQueue, ReconciliationResult,
                        SendLog, Vendor)
from app.reconcile import reconcile_batch, requeue_after_reason, requeue_vendor_exceptions
from app.sending import NotConfigured, run_due, send_on_date
from tests.fixtures import special_cases as sc
from tests.fixtures import three_row_example as fx
from tests.util import files_from

ALL_DUE = date(2025, 9, 17)  # both fixture emails are due by then (Mon 15th and Wed 17th)


class FakeSMTP:
    """Stands in for smtplib.SMTP. Class attributes configure failures and collect what was sent."""
    sent, connects = [], 0
    fail_connects = 0  # fail this many connections before succeeding
    fail_send = None  # exception raised by send_message

    def __init__(self, host, port, timeout=None):
        FakeSMTP.connects += 1
        if FakeSMTP.fail_connects:
            FakeSMTP.fail_connects -= 1
            raise ConnectionRefusedError("mail server down")

    def starttls(self): pass
    def login(self, user, password): pass
    def quit(self): pass

    def send_message(self, msg):
        if FakeSMTP.fail_send:
            raise FakeSMTP.fail_send
        FakeSMTP.sent.append(msg)
        return {}


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.connects, FakeSMTP.fail_connects, FakeSMTP.fail_send = [], 0, 0, None
    monkeypatch.setattr("app.sending.smtp.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(config, "SMTP_FROM", "payments@sudhamayi.example")
    monkeypatch.setattr(config, "TEST_RECIPIENT", "")
    monkeypatch.delenv("DRY_RUN", raising=False)
    sleeps = []
    monkeypatch.setattr("app.sending.time.sleep", sleeps.append)
    FakeSMTP.sleeps = sleeps
    return FakeSMTP


@pytest.fixture
def no_build_queue(monkeypatch):
    calls = []
    monkeypatch.setattr("app.reconcile.build_queue", lambda session, **kw: calls.append(kw) or [])
    return calls


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")


def queue_fixture(db) -> list[EmailQueue]:
    """The three-row example reconciled, plus its two emails queued by hand (one per payment date)."""
    batch = ingest_batch(db, files_from(fx))
    reconcile_batch(db, batch.id)
    by_invoice = {e.invoice_no: r for r, e in db.execute(
        select(ReconciliationResult, ConsolidatedEntry)
        .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id))}
    queues = []
    for paid, invoices in fx.EMAIL_GROUPS.items():
        q = EmailQueue(vendor_id=by_invoice[invoices[0]].vendor_id, send_on_date=fx.SEND_ON_DATES[paid])
        db.add(q)
        db.flush()
        db.add_all(EmailItem(email_queue_id=q.id, reconciliation_result_id=by_invoice[i].id,
                             utr=db.get(ConsolidatedEntry, by_invoice[i].consolidated_entry_id).utr) for i in invoices)
        queues.append(q)
    db.commit()
    return queues


def history(db, status=None) -> list[EmailHistory]:
    q = select(EmailHistory).order_by(EmailHistory.id)
    return list(db.scalars(q.where(EmailHistory.status == status) if status else q))


def test_send_on_date_skips_sundays_only():
    assert send_on_date(date(2025, 9, 11)) == date(2025, 9, 13)  # Thu -> Sat
    assert send_on_date(date(2025, 9, 12)) == date(2025, 9, 15)  # Fri -> Mon (Sunday skipped)
    assert send_on_date(date(2025, 9, 13)) == date(2025, 9, 16)  # Sat -> Tue
    assert send_on_date(date(2025, 9, 15)) == date(2025, 9, 17)  # Mon -> Wed


def test_dry_run_is_the_default_and_sends_nothing(db, smtp, no_build_queue):
    queue_fixture(db)
    assert run_due(db, ALL_DUE) == {"sent": 0, "failed": 0, "dry_run": 2, "not_sent": 0}
    assert smtp.connects == 0 and smtp.sent == []
    assert {q.status for q in db.scalars(select(EmailQueue))} == {"PENDING"}  # still due once DRY_RUN is off
    assert len(history(db, "DRY_RUN")) == 3
    run_due(db, ALL_DUE)
    assert len(history(db, "DRY_RUN")) == 3  # a re-run adds no duplicate rows


def test_sends_once_even_when_run_twice(db, smtp, no_build_queue, live):
    queue_fixture(db)
    assert run_due(db, ALL_DUE)["sent"] == 2
    assert run_due(db, ALL_DUE) == {"sent": 0, "failed": 0, "dry_run": 0, "not_sent": 0}
    assert len(smtp.sent) == 2
    assert [m["To"] for m in smtp.sent] == [fx.VENDOR["email"]] * 2
    assert {q.status for q in db.scalars(select(EmailQueue))} == {"SENT"}
    sent = history(db, "SENT")
    assert sorted(h.utr for h in sent) == sorted(e["utr"] for e in fx.CONSOLIDATED_ENTRIES)  # one row per UTR
    assert all(h.sent_at and h.email_queue_id and h.to_email == fx.VENDOR["email"] for h in sent)
    assert db.scalar(select(func.count()).select_from(SendLog).where(SendLog.status == "SENT")) == 2


def test_only_due_emails_go(db, smtp, no_build_queue, live):
    queue_fixture(db)
    assert run_due(db, date(2025, 9, 15))["sent"] == 1  # the Wed 17th email waits
    assert {h.invoice_no for h in history(db, "SENT")} == {"INV-2305", "INV-2310"}


def test_test_recipient_redirects_everything(db, smtp, no_build_queue, live, monkeypatch):
    monkeypatch.setattr(config, "TEST_RECIPIENT", "qa-inbox@sudhamayi.example")
    queue_fixture(db)
    run_due(db, ALL_DUE)
    assert {m["To"] for m in smtp.sent} == {"qa-inbox@sudhamayi.example"}
    assert all(m["Subject"].startswith(f"[TEST for {fx.VENDOR['email']}]") for m in smtp.sent)


def test_retries_when_the_server_is_unreachable_then_sends_once(db, smtp, no_build_queue, live):
    queue_fixture(db)
    smtp.fail_connects = 2
    assert run_due(db, date(2025, 9, 15))["sent"] == 1
    assert len(smtp.sent) == 1 and smtp.sleeps == [2, 4]  # backoff


def test_failed_after_n_attempts_and_never_retried(db, smtp, no_build_queue, live):
    queue_fixture(db)
    smtp.fail_connects = 99
    assert run_due(db, date(2025, 9, 15))["failed"] == 1
    assert smtp.connects == 3 and smtp.sent == []
    failed = history(db, "FAILED")
    assert len(failed) == 2 and all("attempt 3" in h.error_message for h in failed)
    smtp.fail_connects = 0
    run_due(db, date(2025, 9, 15))  # FAILED is final: a later run doesn't retry it
    assert smtp.sent == [] and len(history(db, "FAILED")) == 2


def test_failure_after_handing_over_is_not_retried(db, smtp, no_build_queue, live):
    import smtplib
    queue_fixture(db)
    smtp.fail_send = smtplib.SMTPServerDisconnected("connection lost after DATA")
    assert run_due(db, date(2025, 9, 15))["failed"] == 1
    assert smtp.connects == 1  # it may have been delivered: never try again
    assert "may or may not have been delivered" in history(db, "FAILED")[0].error_message


def test_claimed_rows_are_left_alone(db, smtp, no_build_queue, live):
    first, second = queue_fixture(db)
    first.status = "SENDING"  # another run holds it (or one died mid-send)
    db.commit()
    assert run_due(db, ALL_DUE)["sent"] == 1
    assert db.get(EmailQueue, first.id).status == "SENDING"


def test_two_runs_racing_never_send_twice(db, smtp, no_build_queue, live, monkeypatch):
    """Another run claims every row just after this run listed them as due: this run must send nothing."""
    queue_fixture(db)
    real_scalars, raced = db.scalars, []

    def scalars_then_other_run_claims(stmt, *args, **kwargs):
        rows = real_scalars(stmt, *args, **kwargs).all()
        if not raced:
            raced.append(True)
            with Session(db.get_bind()) as other:  # a second worker, own connection
                other.execute(update(EmailQueue).values(status="SENDING"))
                other.commit()
        return type("Rows", (), {"all": lambda self: rows})()
    monkeypatch.setattr(db, "scalars", scalars_then_other_run_claims)
    assert run_due(db, ALL_DUE)["sent"] == 0
    assert smtp.connects == 0


def test_no_email_for_blocked_invoices_or_already_sent_utrs(db, smtp, no_build_queue, live):
    first, second = queue_fixture(db)
    result_id = db.scalar(select(EmailItem.reconciliation_result_id).where(EmailItem.email_queue_id == first.id))
    db.get(ReconciliationResult, result_id).status = "MANUAL_REVIEW"
    utr = db.scalar(select(EmailItem.utr).where(EmailItem.email_queue_id == second.id))
    db.add(EmailHistory(vendor_name="X", utr=utr, status="SENT"))  # emailed before by some other path
    db.commit()
    assert run_due(db, ALL_DUE) == {"sent": 0, "failed": 0, "dry_run": 0, "not_sent": 2}
    assert smtp.connects == 0
    assert {q.status for q in db.scalars(select(EmailQueue))} == {"SKIPPED"}


def test_invalid_vendor_email_is_skipped(db, smtp, no_build_queue, live):
    queue_fixture(db)
    db.scalar(select(Vendor)).is_email_valid = False
    db.commit()
    assert run_due(db, ALL_DUE)["not_sent"] == 2 and smtp.connects == 0


def test_refuses_to_send_without_smtp(db, smtp, no_build_queue, live, monkeypatch):
    queue_fixture(db)
    monkeypatch.setattr(config, "SMTP_HOST", "")
    with pytest.raises(NotConfigured):
        run_due(db, ALL_DUE)
    assert {q.status for q in db.scalars(select(EmailQueue))} == {"PENDING"}  # nothing claimed


def test_excel_failure_never_blocks_the_run(db, smtp, no_build_queue, live, monkeypatch):
    queue_fixture(db)

    def broken(session):
        raise OSError("history.xlsx is open in Excel")
    monkeypatch.setattr("app.sending.xlsx.append_new_rows", broken)
    assert run_due(db, ALL_DUE)["sent"] == 2
    assert {q.status for q in db.scalars(select(EmailQueue))} == {"SENT"}
    assert run_due(db, ALL_DUE)["sent"] == 0 and len(smtp.sent) == 2


def test_not_sent_history_once_per_utr_and_reason(db, no_build_queue):
    batch = ingest_batch(db, files_from(sc))
    reconcile_batch(db, batch.id)
    blocked = db.scalar(select(func.count()).select_from(ReconciliationResult)
                        .where(ReconciliationResult.status.in_(("EXCEPTION", "MANUAL_REVIEW"))))
    rows = history(db, "NOT_SENT")
    assert len(rows) == blocked == 13
    assert {(h.invoice_no, h.not_sent_reason) for h in rows} >= {("INV-S13", "BOUNCED"), ("INV-S12", "UTR_NOT_FOUND")}
    reconcile_batch(db, batch.id)
    assert len(history(db, "NOT_SENT")) == 13  # a re-run adds nothing


def test_every_outcome_has_exactly_one_history_row(db, smtp, no_build_queue, live):
    queue_fixture(db)
    run_due(db, ALL_DUE)
    run_due(db, ALL_DUE)
    keys = [(h.utr, h.status, h.not_sent_reason) for h in history(db)]
    assert len(keys) == len(set(keys)) == 3


def result_for(db, invoice_no) -> ReconciliationResult:
    return db.scalar(select(ReconciliationResult).join(
        ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
        .where(ConsolidatedEntry.invoice_no == invoice_no))


def test_requeue_after_reason(db, no_build_queue):
    reconcile_batch(db, ingest_batch(db, files_from(sc)).id)
    no_build_queue.clear()
    r = result_for(db, "INV-S06")  # REASON_MISSING, deduction 3,000
    requeue_after_reason(db, r.id, "  Short supply (DN-0999) ")
    db.refresh(r)
    assert (r.status, r.exception_type, r.reason) == ("DEDUCTION", None, "Short supply (DN-0999)")
    assert no_build_queue == [{"result_ids": [r.id]}]
    assert db.scalar(select(AuditLog).order_by(AuditLog.id.desc())).new_value == "Short supply (DN-0999)"
    with pytest.raises(ValueError, match="not waiting"):  # already DEDUCTION now
        requeue_after_reason(db, r.id, "again")
    with pytest.raises(ValueError, match="no deduction"):  # overpaid: no deduction a reason could explain
        requeue_after_reason(db, result_for(db, "INV-S16").id, "x")
    with pytest.raises(ValueError, match="1-500"):
        requeue_after_reason(db, result_for(db, "INV-S05").id, "   ")
    assert len(no_build_queue) == 1


def test_requeue_vendor_exceptions(db, no_build_queue):
    reconcile_batch(db, ingest_batch(db, files_from(sc)).id)
    no_build_queue.clear()
    # INVALID_EMAIL: the vendor page fixes Harkrishan's address
    harkrishan = db.scalar(select(Vendor).where(Vendor.party_name == "Harkrishan Medicals"))
    harkrishan.email, harkrishan.is_email_valid = "accounts@harkrishan.example", True
    db.commit()
    s07 = result_for(db, "INV-S07")
    assert requeue_vendor_exceptions(db, harkrishan.id) == 1
    assert db.get(ReconciliationResult, s07.id).status == "PAID_IN_FULL"
    assert no_build_queue == [{"result_ids": [s07.id]}]
    # VENDOR_NOT_FOUND: the missing vendor is added; only that vendor's invoice moves
    unknown = Vendor(party_name="Unknown Traders", email="ut@unknown.example", is_email_valid=True)
    db.add(unknown)
    db.commit()
    assert requeue_vendor_exceptions(db, unknown.id) == 1
    assert result_for(db, "INV-S08").vendor_id == unknown.id
    assert result_for(db, "INV-S24").status == "EXCEPTION"  # Nova Labs: still ambiguous, untouched
    assert requeue_vendor_exceptions(db, unknown.id) == 0  # nothing left
    with pytest.raises(ValueError):
        requeue_vendor_exceptions(db, 999)


def test_run_now_endpoint(client, db, smtp, no_build_queue, monkeypatch):
    queue_fixture(db)  # 2025 send dates: both due by today's real date
    r = client.post("/api/scheduler/run-now")
    assert r.status_code == 200 and "x-stub" not in r.headers
    assert r.json() == {"sent": 0, "failed": 0, "dry_run": 2, "not_sent": 0}  # DRY_RUN by default
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr(config, "SMTP_HOST", "")
    r = client.post("/api/scheduler/run-now")
    assert r.status_code == 503 and "SMTP" in r.json()["detail"]


def test_scheduler_job_uses_send_time(monkeypatch):
    from app.routers.scheduler import build_scheduler
    monkeypatch.setenv("SEND_TIME", "09:30")
    job = build_scheduler().get_job("t_plus_2_send")
    assert str(job.trigger) == "cron[hour='9', minute='30']" and str(job.trigger.timezone) == "Asia/Kolkata"
    monkeypatch.setenv("SEND_TIME", "nonsense")
    assert str(build_scheduler().get_job("t_plus_2_send").trigger) == "cron[hour='10', minute='0']"
