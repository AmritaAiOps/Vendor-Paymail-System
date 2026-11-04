from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.contract import QueueStatus
from app.email_builder import render_email
from app.models import ConsolidatedEntry, EmailItem, EmailQueue, ReconciliationResult, Vendor, get_db
from app.schemas import EmailPreview, QueueItemOut, RunNowOut, ScheduledOut
from app.sending import NotConfigured, send_now

router = APIRouter(prefix="/email-queue", tags=["email-queue"])


@router.get("", response_model=list[QueueItemOut])
def queue(batch_id: int | None = None, status: QueueStatus | None = None, db: Session = Depends(get_db)):
    q = (select(EmailQueue, Vendor, func.count(EmailItem.id))
         .join(Vendor, Vendor.id == EmailQueue.vendor_id)
         .join(EmailItem, EmailItem.email_queue_id == EmailQueue.id)
         .group_by(EmailQueue.id, Vendor.id).order_by(EmailQueue.send_on_date, EmailQueue.id))
    if status is not None:
        q = q.where(EmailQueue.status == status)
    if batch_id is not None:
        q = (q.join(ReconciliationResult, ReconciliationResult.id == EmailItem.reconciliation_result_id)
             .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
             .where(ConsolidatedEntry.batch_id == batch_id))  # count then covers only that batch's invoices
    return [QueueItemOut(id=eq.id, vendor_id=v.id, vendor_name=v.party_name, to_email=v.email,
                         send_on_date=eq.send_on_date, status=eq.status, sent_at=eq.sent_at,
                         subject=eq.subject, invoice_count=n)
            for eq, v, n in db.execute(q)]


@router.post("/schedule", response_model=ScheduledOut, dependencies=[Depends(require_admin)])
def schedule(batch_id: int | None = None, db: Session = Depends(get_db)):
    """Send all: every DRAFT email (only those holding the batch's invoices, if batch_id) becomes PENDING, so the
    daily job sends it on its T+2 date. An email whose date has passed goes on the next run."""
    q = update(EmailQueue).where(EmailQueue.status == QueueStatus.DRAFT)
    if batch_id is not None:
        q = q.where(EmailQueue.id.in_(
            select(EmailItem.email_queue_id)
            .join(ReconciliationResult, ReconciliationResult.id == EmailItem.reconciliation_result_id)
            .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
            .where(ConsolidatedEntry.batch_id == batch_id)))
    n = db.execute(q.values(status=QueueStatus.PENDING)).rowcount
    db.commit()
    return ScheduledOut(scheduled=n)


@router.post("/{id}/send-now", response_model=RunNowOut, dependencies=[Depends(require_admin)])
def send_one_now(id: int, db: Session = Depends(get_db)):
    """Send this one email now, ignoring its T+2 date. 409 if it was already sent or is being sent; 503 as run-now."""
    try:
        outcome = send_now(db, id)
    except NotConfigured as e:
        raise HTTPException(503, str(e))
    if outcome is None:
        raise HTTPException(409, "This email was already sent, or is being sent")
    return RunNowOut(**{"sent": 0, "failed": 0, "dry_run": 0, "not_sent": 0, outcome: 1})


@router.get("/{id}/preview", response_model=EmailPreview)
def preview(id: int, db: Session = Depends(get_db)):
    try:
        subject, html, text = render_email(db, id)
    except LookupError:
        raise HTTPException(404, "Email queue entry not found")
    queue_row = db.get(EmailQueue, id)
    if queue_row.status == QueueStatus.SENT and queue_row.body_html:
        # the sender stores what it actually sent; show that, not a fresh render (the signature may have changed since).
        # shortcut: the plain-text part is still re-rendered, only subject and HTML are kept as sent
        subject, html = queue_row.subject or subject, queue_row.body_html
    return EmailPreview(subject=subject, html=html, text=text)
