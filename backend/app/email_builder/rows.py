"""The one row builder: feeds the email table and the proforma, so they can never disagree."""
import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract import ResultStatus
from app.models import ConsolidatedEntry, ReconciliationResult, Vendor

HEADER = ["Invoice No", "Invoice Amount", "UTR", "Payment Date", "Amount Paid",
          "TDS Amount", "Invoice Deduction", "Reason"]
SENDABLE = (ResultStatus.PAID_IN_FULL, ResultStatus.TDS_ONLY, ResultStatus.DEDUCTION)


def inr(v: Decimal | None) -> str:
    """5545060.5 -> '55,45,060.50' (Indian grouping). None -> ''."""
    if v is None:
        return ""
    whole, frac = f"{v:.2f}".split(".")
    sign, whole = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    head, tail = whole[:-3], whole[-3:]
    head = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
    return f"{sign}{head + ',' if head else ''}{tail}.{frac}"


def day(d: date | None) -> str:
    return d.strftime("%d-%b-%y") if d else ""


def row(res: ReconciliationResult, entry: ConsolidatedEntry) -> list[str]:
    """Cells in HEADER order. Optional cells that don't apply (NULL or zero) stay empty."""
    return [entry.invoice_no, inr(res.invoice_value), entry.utr or "", day(res.payment_date), inr(res.amount_paid),
            inr(res.tds_amount) if res.tds_amount else "",
            inr(res.invoice_deduction) if res.invoice_deduction else "",
            (res.reason or "") if res.invoice_deduction else ""]  # reason belongs to the deduction only


def _key(name: str) -> str:
    # shortcut: letters and digits only, lower-cased. A's ingest.clean.name_key also folds Pvt/Ltd/Co/&;
    # we may not import ingest, so ask A for a contract-level vendor id on results if names ever disagree.
    return re.sub(r"[^a-z0-9]", "", name.lower())


def sendable(session: Session, batch_id: int | None = None, result_ids: list[int] | None = None):
    """(Vendor, result, entry) for results that get an email, oldest invoice first. Others are skipped."""
    q = (select(ReconciliationResult, ConsolidatedEntry)
         .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
         .where(ReconciliationResult.status.in_(SENDABLE), ReconciliationResult.payment_date.is_not(None))
         .order_by(ReconciliationResult.id))
    if batch_id is not None:
        q = q.where(ConsolidatedEntry.batch_id == batch_id)
    if result_ids is not None:
        q = q.where(ReconciliationResult.id.in_(result_ids))
    vendors = {_key(v.party_name): v for v in session.scalars(select(Vendor))}
    return [(vendors[k], r, e) for r, e in session.execute(q) if (k := _key(e.vendor_name)) in vendors and e.utr]
