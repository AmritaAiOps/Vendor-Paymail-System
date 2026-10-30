"""Reconciliation. Owner: Person A.

decide() is the whole rule set for one invoice: one if/elif chain over plain values, no DB.
reconcile_batch() gathers those values for every consolidated entry of a batch with dict lookups,
stores the results, then hands the batch to email_builder.build_queue (Person B).

The rule, checked against the Aug-Sep 2026 files (2,024 of 2,143 rows reconcile exactly):
  shortfall = invoice value - bank debit
  shortfall = TDS (TDS file) + goods deduction (GDN Report), each within INR 1.
Anything that doesn't add up goes to MANUAL_REVIEW, so an email only goes out when the numbers agree."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contract import BatchStatus, ExceptionType as Ex, ResultStatus as St
from app.email_builder import build_queue
from app.ingest.clean import loose_name_key, name_key
from app.models import (BankTransaction, ConsolidatedEntry, EmailItem, GdnRecord, ReconciliationResult, TdsRecord,
                        UploadBatch, Vendor)

ROUNDING = Decimal("1.00")  # differences up to INR 1 are rounding


def payment_date(bank: BankTransaction) -> date:
    """The one place that decides what "payment date" means. Today: the bank value date."""
    return bank.value_date


def decide(invoice_value: Decimal, bank: BankTransaction | None, tds: Decimal | None, gdn_amount: Decimal | None,
           gdn_reason: str | None, vendor: Vendor | None) -> dict:
    """reconciliation_results fields for one invoice. Hard exceptions (no payment, bounced, no vendor, bad email)
    come first: they need a data fix, after which the invoice is decided again from scratch.
    Empty means NULL: a TDS or deduction that doesn't apply is None, never 0."""
    fields = {"invoice_value": invoice_value, "bank_txn_id": None, "vendor_id": vendor.id if vendor else None,
              "payment_date": None, "amount_paid": None, "tds_amount": None, "invoice_deduction": None, "reason": None}

    def result(status: St, exception_type: Ex | None = None, **amounts) -> dict:
        return {**fields, **amounts, "status": status, "exception_type": exception_type}

    if bank is None:
        return result(St.EXCEPTION, Ex.UTR_NOT_FOUND)
    fields.update(bank_txn_id=bank.id, payment_date=payment_date(bank), amount_paid=bank.debit)
    if bank.is_bounced:
        return result(St.EXCEPTION, Ex.BOUNCED)
    if vendor is None:
        return result(St.EXCEPTION, Ex.VENDOR_NOT_FOUND)
    if not vendor.is_email_valid:
        return result(St.EXCEPTION, Ex.INVALID_EMAIL)

    shortfall = invoice_value - bank.debit
    tds, gdn = tds or Decimal(0), gdn_amount or Decimal(0)
    if shortfall < -ROUNDING:  # paid more than invoiced
        return result(St.MANUAL_REVIEW, Ex.AMOUNT_MISMATCH)
    if shortfall <= ROUNDING:
        return result(St.PAID_IN_FULL)
    if tds > shortfall + ROUNDING:
        return result(St.MANUAL_REVIEW, Ex.AMOUNT_MISMATCH, tds_amount=tds)
    if gdn and abs(shortfall - tds - gdn) <= ROUNDING:  # TDS (possibly none) + goods deduction
        deduction, tds_cut = shortfall - tds, tds or None
    elif gdn and abs(shortfall - gdn) <= ROUNDING:  # TDS is listed but wasn't cut from this payment
        deduction, tds_cut = shortfall, None
    elif tds and shortfall - tds <= ROUNDING:
        return result(St.TDS_ONLY, tds_amount=tds)
    elif gdn:  # a debit note exists but doesn't match the shortfall: its reason can't be trusted for it
        return result(St.MANUAL_REVIEW, Ex.AMOUNT_MISMATCH, tds_amount=tds or None, invoice_deduction=shortfall - tds)
    else:
        return result(St.MANUAL_REVIEW, Ex.REASON_MISSING, tds_amount=tds or None, invoice_deduction=shortfall - tds)
    if not gdn_reason:  # never send a deduction without its reason
        return result(St.MANUAL_REVIEW, Ex.REASON_MISSING, tds_amount=tds_cut, invoice_deduction=deduction)
    return result(St.DEDUCTION, tds_amount=tds_cut, invoice_deduction=deduction, reason=gdn_reason)


class _ByInvoice:
    """Totals (and distinct reasons) per (vendor, invoice) from a batch's TDS or GDN rows."""

    def __init__(self, rows, amount: str, reason: str | None = None):
        self.totals = defaultdict(lambda: [Decimal(0), []])
        self.vendors = defaultdict(set)  # invoice no -> vendor keys that use it in this file
        for r in rows:
            if not r.invoice_no:
                continue
            entry = self.totals[(name_key(r.vendor_name), r.invoice_no)]
            entry[0] += getattr(r, amount) or 0
            text = getattr(r, reason) if reason else None
            if text and text not in entry[1]:
                entry[1].append(text)
            self.vendors[r.invoice_no].add(name_key(r.vendor_name))

    def get(self, vendor_name: str, invoice_no: str, invoice_unique: bool) -> tuple[Decimal | None, str | None]:
        """Match on vendor + invoice. If this file spells the vendor differently, fall back to the invoice number
        alone, but only when it's unambiguous in both this file and the consolidated report."""
        key = (name_key(vendor_name), invoice_no)
        others = self.vendors.get(invoice_no, set())
        if key not in self.totals and invoice_unique and len(others) == 1:
            key = (next(iter(others)), invoice_no)
        if key not in self.totals:
            return None, None
        total, reasons = self.totals[key]
        return total, "; ".join(reasons) or None


class _Vendors:
    """Vendor lookup: exact name_key first; else the loose key, but only if it points at exactly one vendor."""

    def __init__(self, vendors):
        self.exact, self.loose = {}, defaultdict(list)
        for v in vendors:
            self.exact[name_key(v.party_name)] = v
            self.loose[loose_name_key(v.party_name)].append(v)

    def find(self, name: str | None) -> Vendor | None:
        if not name:
            return None
        found = self.loose.get(loose_name_key(name), [])
        return self.exact.get(name_key(name)) or (found[0] if len(found) == 1 else None)


def reconcile_batch(session: Session, batch_id: int) -> None:
    """Decide every consolidated entry of the batch and store the results (re-runnable: an existing result is
    recomputed unless it's already queued for email). Then calls build_queue for the batch and commits."""
    where = lambda model: select(model).where(model.batch_id == batch_id)
    entries = session.scalars(where(ConsolidatedEntry).order_by(ConsolidatedEntry.id)).all()
    bank = {}
    for b in session.scalars(where(BankTransaction).order_by(BankTransaction.id)):
        bank.setdefault(b.utr, b)  # strict UTR match; the statement's UTRs are unique for vendor payments
    tds = _ByInvoice(session.scalars(where(TdsRecord)), "tds_amount")
    gdn = _ByInvoice(session.scalars(where(GdnRecord)), "amount", "reason")
    vendors = _Vendors(session.scalars(select(Vendor)))
    invoice_vendors = defaultdict(set)
    for e in entries:
        invoice_vendors[e.invoice_no].add(name_key(e.vendor_name))

    existing = {r.consolidated_entry_id: r for r in session.scalars(
        select(ReconciliationResult).where(ReconciliationResult.consolidated_entry_id.in_([e.id for e in entries])))}
    queued = set(session.scalars(select(EmailItem.reconciliation_result_id).where(
        EmailItem.reconciliation_result_id.in_([r.id for r in existing.values()]))))

    for e in entries:
        b = bank.get(e.utr) if e.utr else None
        vendor = vendors.find(e.vendor_name) or (vendors.find(b.vendor_name) if b else None)  # bank name: 2nd try
        unique = len(invoice_vendors[e.invoice_no]) == 1
        tds_amount, _ = tds.get(e.vendor_name, e.invoice_no, unique)
        gdn_amount, reason = gdn.get(e.vendor_name, e.invoice_no, unique)
        fields = decide(e.invoice_amount, b, tds_amount, gdn_amount, reason, vendor)
        result = existing.get(e.id)
        if result is None:
            session.add(ReconciliationResult(consolidated_entry_id=e.id, **fields))
        elif result.id not in queued:
            for k, v in fields.items():
                setattr(result, k, v)

    session.get(UploadBatch, batch_id).status = BatchStatus.RECONCILED
    session.commit()
    build_queue(session, batch_id=batch_id)  # Person B: creates email_queue / email_items for this batch
    session.commit()


def requeue_after_reason(session: Session, result_id: int, reason: str) -> None:
    """Set the reason on a MANUAL_REVIEW result, move it to DEDUCTION, audit, and queue it via
    email_builder.build_queue(result_ids=[result_id]). ValueError if the result is not MANUAL_REVIEW."""
    # STUB(contract): Person A replaces this. Do-nothing until then.
    return None


def requeue_vendor_exceptions(session: Session, vendor_id: int) -> int:
    """Re-check this vendor's VENDOR_NOT_FOUND / INVALID_EMAIL results (e.g. after an email fix) and queue
    the ones that now pass. Returns how many were queued."""
    # STUB(contract): Person A replaces this. Do-nothing until then.
    return 0
