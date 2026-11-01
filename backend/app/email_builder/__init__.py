"""Email queue and rendering. Owner: Person B."""
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.contract import QueueStatus
from app.email_builder.rows import HEADER, row, sendable
from app.models import ConsolidatedEntry, EmailItem, EmailQueue, ReconciliationResult, Vendor

COMPANY = "Sudhamayi Enterprises Pvt. Ltd."
SIGNATURE_PLACEHOLDER = "[Name, designation]"
# autoescape covers .html only; the text template is plain text
_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))


def _signature() -> str:
    try:
        return config.get_setting("signature")
    except KeyError:  # shortcut: config.SETTINGS lacks "signature" until A pushes it, drop this try/except when it lands
        return SIGNATURE_PLACEHOLDER


def build_queue(session: Session, batch_id: int | None = None, result_ids: list[int] | None = None) -> list[int]:
    """Create email_queue + email_items rows (one queue row per vendor + send date, one item per UTR)
    for sendable results of a batch, or for the given results. Skips UTRs already in email_items.
    Returns the new email_queue ids."""
    from app.sending import send_on_date  # here, not at the top: sending imports render_email from this module

    found = sendable(session, batch_id, result_ids)
    already = set(session.scalars(select(EmailItem.utr).where(EmailItem.utr.in_([e.utr for _, _, e in found]))))
    groups = defaultdict(list)
    for vendor, res, entry in found:
        if entry.utr not in already:
            already.add(entry.utr)  # same UTR twice in one run
            groups[(vendor.id, send_on_date(res.payment_date))].append((res, entry))

    new_ids = []
    for (vendor_id, due), items in groups.items():
        # a still-pending email for the same vendor and day takes the new rows, so they stay one email
        queue = session.scalar(select(EmailQueue).where(
            EmailQueue.vendor_id == vendor_id, EmailQueue.send_on_date == due, EmailQueue.status == QueueStatus.PENDING))
        created = queue is None
        try:
            if created:
                queue = EmailQueue(vendor_id=vendor_id, send_on_date=due, status=QueueStatus.PENDING)
                session.add(queue)
                session.flush()
            session.add_all(EmailItem(email_queue_id=queue.id, reconciliation_result_id=res.id, utr=entry.utr)
                            for res, entry in items)
            session.flush()
            queue.subject, queue.body_html, _ = render_email(session, queue.id)
            session.commit()
        except IntegrityError:  # another writer queued one of these UTRs first: UNIQUE(utr) held, leave the group
            session.rollback()
            continue
        if created:
            new_ids.append(queue.id)
    return new_ids


def render_email(session: Session, queue_id: int) -> tuple[str, str, str]:
    """Return (subject, html, text) for one email_queue row. Table columns in contract order; empty cells stay empty."""
    queue = session.get(EmailQueue, queue_id)
    if queue is None:
        raise LookupError(f"email_queue {queue_id} not found")
    vendor = session.get(Vendor, queue.vendor_id)
    pairs = session.execute(
        select(ReconciliationResult, ConsolidatedEntry)
        .join(EmailItem, EmailItem.reconciliation_result_id == ReconciliationResult.id)
        .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
        .where(EmailItem.email_queue_id == queue_id).order_by(EmailItem.id))
    ctx = dict(vendor_name=vendor.party_name, header=HEADER, rows=[row(r, e) for r, e in pairs],
               signature=_signature(), company=COMPANY)
    return (f"Payment Details – {vendor.party_name} – {COMPANY}",
            _env.get_template("email.html").render(ctx), _env.get_template("email.txt").render(ctx))
