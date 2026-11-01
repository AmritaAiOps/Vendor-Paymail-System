"""T+2 sending and the email_history writer. Owner: Person A.

run_due() is the daily job. Every PENDING email_queue row with send_on_date <= today is:
  1. claimed: PENDING -> SENDING in one conditional UPDATE, so two runs (scheduler, run-now, two app workers)
     can never both take a row;
  2. checked: vendor email valid, every invoice sendable, no UTR already emailed;
  3. rendered by Person B's email_builder.render_email (this module never builds an email);
  4. sent, or in DRY_RUN only logged;
  5. finished in one transaction: queue status + send_logs row + email_history rows.
Only failures where nothing reached the mail server are retried. A row left in SENDING means a run died
mid-send; it is never retried automatically, because the mail may already have gone."""
import logging
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app import config
from app.contract import ExceptionType, HistoryStatus, QueueStatus, ResultStatus
from app.email_builder import render_email
from app.history import xlsx
from app.ingest.clean import split_emails
from app.models import (ConsolidatedEntry, EmailHistory, EmailItem, EmailQueue, ReconciliationResult, SendLog,
                        SessionLocal, Vendor)
from app.sending.smtp import SendError, deliver

log = logging.getLogger(__name__)

SENDABLE = {ResultStatus.PAID_IN_FULL, ResultStatus.TDS_ONLY, ResultStatus.DEDUCTION}
ATTEMPTS = 3  # tries per email, only for failures where nothing reached the server
BACKOFF_SECONDS = 2  # waits 2 s, then 4 s


class NotConfigured(RuntimeError):
    """Real sending was asked for but SMTP isn't set up. Nothing is claimed or changed."""


def send_on_date(payment_date: date) -> date:
    """T+2 business days. Every day except Sunday is a business day; holidays are not skipped."""
    # shortcut: the 2 is fixed, not config.get_setting("send_offset_days"); the contract has no such setting yet
    d, left = payment_date, 2
    while left:
        d += timedelta(days=1)
        if d.weekday() != 6:  # Sunday
            left -= 1
    return d


def today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def dry_run() -> bool:
    """True unless the dry_run setting is explicitly off: anything unclear means don't send."""
    return config.get_setting("dry_run").strip().lower() not in ("false", "0", "no", "off")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is(column, value):
    return column.is_(None) if value is None else column == value


def record_history(session: Session, status: HistoryStatus, items: list, *, queue: EmailQueue | None = None,
                   not_sent_reason: ExceptionType | None = None, to_email: str | None = None,
                   subject: str | None = None, error: str | None = None, sent_at: datetime | None = None) -> int:
    """The only writer of email_history (append-only), one row per (result, entry) item. Doesn't commit: the caller
    commits it together with the status change. DRY_RUN and NOT_SENT rows are written once per UTR (per vendor +
    invoice when there's no UTR) and reason, so re-runs add nothing. Returns the number of rows written."""
    written = 0
    for result, entry in items:
        if status in (HistoryStatus.DRY_RUN, HistoryStatus.NOT_SENT):
            same = (EmailHistory.utr == entry.utr) if entry.utr else (
                EmailHistory.utr.is_(None) & (EmailHistory.invoice_no == entry.invoice_no)
                & (EmailHistory.vendor_name == entry.vendor_name))
            if session.scalar(select(exists().where(same, EmailHistory.status == status,
                                                    _is(EmailHistory.not_sent_reason, not_sent_reason)))):
                continue
        session.add(EmailHistory(
            batch_id=entry.batch_id, vendor_name=entry.vendor_name, to_email=to_email, subject=subject,
            invoice_no=entry.invoice_no, utr=entry.utr, invoice_amount=result.invoice_value,
            payment_date=result.payment_date, amount_paid=result.amount_paid, tds_amount=result.tds_amount,
            invoice_deduction=result.invoice_deduction, reason=result.reason, status=status,
            not_sent_reason=not_sent_reason, scheduled_send_date=queue.send_on_date if queue else None,
            sent_at=sent_at, error_message=error, email_queue_id=queue.id if queue else None))
        written += 1
    return written


def run_due(session: Session, on: date | None = None) -> dict:
    """Send everything due on or before `on` (default: today in Asia/Kolkata). Returns counts per outcome."""
    on = on or today()
    dry = dry_run()
    if not dry and not (config.SMTP_HOST and config.SMTP_FROM):
        raise NotConfigured("SMTP_HOST / SMTP_FROM not set: refusing to send (DRY_RUN=true previews instead)")
    counts = {"sent": 0, "failed": 0, "dry_run": 0, "not_sent": 0}
    due = session.scalars(select(EmailQueue.id)
                          .where(EmailQueue.status == QueueStatus.PENDING, EmailQueue.send_on_date <= on)
                          .order_by(EmailQueue.send_on_date, EmailQueue.id)).all()
    for queue_id in due:
        claimed = session.execute(update(EmailQueue)
                                  .where(EmailQueue.id == queue_id, EmailQueue.status == QueueStatus.PENDING)
                                  .values(status=QueueStatus.SENDING)).rowcount
        session.commit()
        if not claimed:  # another run took it
            continue
        try:
            counts[_send_one(session, queue_id, dry)] += 1
        except Exception:  # a bug, not a send failure: leave it SENDING (it may have gone) and keep going
            session.rollback()
            log.exception("email_queue %s stopped mid-run and stays SENDING; check it by hand", queue_id)
            counts["failed"] += 1
    append_history_xlsx(session)
    return counts


def append_history_xlsx(session: Session) -> None:
    """Person B's Excel copy of the history. Its failure is logged and never affects sending or statuses."""
    try:
        xlsx.append_new_rows(session)
    except Exception:
        session.rollback()
        log.exception("history.xlsx.append_new_rows failed; the database history is unaffected")


def _send_one(session: Session, queue_id: int, dry: bool) -> str:
    queue = session.get(EmailQueue, queue_id)
    vendor = session.get(Vendor, queue.vendor_id)
    items = session.execute(
        select(ReconciliationResult, ConsolidatedEntry)
        .join(EmailItem, EmailItem.reconciliation_result_id == ReconciliationResult.id)
        .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
        .where(EmailItem.email_queue_id == queue_id).order_by(ConsolidatedEntry.id)).all()

    recipients = split_emails(vendor.email)[0] if vendor and vendor.is_email_valid else []
    problem = _why_not_send(session, recipients, items)
    if problem:
        queue.status = QueueStatus.SKIPPED
        session.add(SendLog(email_queue_id=queue_id, status=HistoryStatus.NOT_SENT, error_message=problem))
        session.commit()
        log.warning("email_queue %s skipped: %s", queue_id, problem)
        return "not_sent"

    to = [config.TEST_RECIPIENT] if config.TEST_RECIPIENT else recipients
    try:
        subject, html, text = render_email(session, queue_id)
    except Exception as e:
        return _finish_failed(session, queue, items, ", ".join(to), None, f"render_email failed: {e}")
    if config.TEST_RECIPIENT:
        subject = f"[TEST for {', '.join(recipients)}] {subject}"

    if dry:
        queue.status = QueueStatus.PENDING  # still due: it goes out on the first run after DRY_RUN is turned off
        if record_history(session, HistoryStatus.DRY_RUN, items, queue=queue, to_email=", ".join(to), subject=subject):
            session.add(SendLog(email_queue_id=queue_id, status=HistoryStatus.DRY_RUN))
        session.commit()
        return "dry_run"

    error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            refused = deliver(to, subject, html, text)
            error = f"refused recipients: {refused}" if refused else None
            break
        except SendError as e:
            if not e.retry_safe or attempt == ATTEMPTS:
                return _finish_failed(session, queue, items, ", ".join(to), subject, f"attempt {attempt}: {e}")
            log.warning("email_queue %s attempt %s failed, retrying: %s", queue_id, attempt, e)
            time.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))

    now = _utcnow()
    queue.status, queue.sent_at, queue.subject, queue.body_html = QueueStatus.SENT, now, subject, html
    session.add(SendLog(email_queue_id=queue_id, status=HistoryStatus.SENT, error_message=error))
    record_history(session, HistoryStatus.SENT, items, queue=queue, to_email=", ".join(to), subject=subject, sent_at=now)
    session.commit()
    return "sent"


def _why_not_send(session: Session, recipients: list[str], items: list) -> str | None:
    if not items:
        return "no invoices in this email"
    if not recipients:
        return "vendor has no valid email address"
    blocked = [f"{e.invoice_no} is {r.status}" for r, e in items if r.status not in SENDABLE]
    if blocked:  # never email an EXCEPTION or MANUAL_REVIEW invoice
        return "not sendable: " + "; ".join(blocked)
    utrs = [e.utr for _, e in items]
    if session.scalar(select(exists().where(EmailHistory.utr.in_(utrs), EmailHistory.status == HistoryStatus.SENT))):
        return "a UTR in this email was already emailed"
    return None


def _finish_failed(session, queue, items, to_email, subject, error) -> str:
    queue.status = QueueStatus.FAILED
    session.add(SendLog(email_queue_id=queue.id, status=HistoryStatus.FAILED, error_message=error))
    record_history(session, HistoryStatus.FAILED, items, queue=queue, to_email=to_email, subject=subject, error=error)
    session.commit()
    log.error("email_queue %s FAILED: %s", queue.id, error)
    return "failed"


def scheduled_run() -> None:
    with SessionLocal() as session:
        try:
            log.info("scheduled email run: %s", run_due(session))
        except Exception:
            log.exception("scheduled email run failed")


def send_time() -> tuple[int, int]:
    """(hour, minute) from the send_time setting; the default 10:00 if the stored value is unreadable."""
    try:
        hour, minute = (int(x) for x in config.get_setting("send_time").split(":"))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    except ValueError:
        pass
    log.error("send_time setting %r is not HH:MM; using 10:00", config.get_setting("send_time"))
    return 10, 0
