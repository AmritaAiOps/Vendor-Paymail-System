"""Reconciliation results as API rows and as an Excel report (used by exceptions, manual review and the batch report)."""
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.email_builder.rows import day, inr
from app.models import ConsolidatedEntry, EmailItem, EmailQueue, ReconciliationResult
from app.reports import export
from app.schemas import ResultOut

HEADERS = ["Vendor", "Invoice No", "Invoice Amount", "UTR", "Payment Date", "Amount Paid", "TDS Amount",
           "Invoice Deduction", "Reason", "Status", "Exception Type", "Send Date"]


def results_out(db: Session, *where) -> list[ResultOut]:
    """ResultOut rows for the matching results: newest batch first, report order inside a batch.
    send_on_date is the queued email's date, null if not queued."""
    q = (select(ReconciliationResult, ConsolidatedEntry, EmailQueue.send_on_date)
         .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
         .outerjoin(EmailItem, EmailItem.reconciliation_result_id == ReconciliationResult.id)
         .outerjoin(EmailQueue, EmailQueue.id == EmailItem.email_queue_id)
         .where(*where).order_by(ConsolidatedEntry.batch_id.desc(), ConsolidatedEntry.id))
    return [ResultOut(id=r.id, batch_id=e.batch_id, vendor_id=r.vendor_id, vendor_name=e.vendor_name, invoice_no=e.invoice_no, utr=e.utr,
                      invoice_value=r.invoice_value, payment_date=r.payment_date, amount_paid=r.amount_paid,
                      tds_amount=r.tds_amount, invoice_deduction=r.invoice_deduction, reason=r.reason,
                      status=r.status, exception_type=r.exception_type, send_on_date=sent)
            for r, e, sent in db.execute(q)]


def results_xlsx(rows: list[ResultOut], title: str, filename: str) -> Response:
    # shortcut: amounts are text in Indian format, like the email and proforma; switch to numeric cells if finance wants to sum them
    wb = export.workbook(title, HEADERS, [28, 16, 16, 22, 14, 16, 14, 18, 30, 16, 18, 14])
    for r in rows:
        export.append(wb.active, [
            r.vendor_name, r.invoice_no, inr(r.invoice_value), r.utr, day(r.payment_date), inr(r.amount_paid),
            inr(r.tds_amount) if r.tds_amount else None, inr(r.invoice_deduction) if r.invoice_deduction else None,
            r.reason, r.status.value, r.exception_type.value if r.exception_type else None, day(r.send_on_date)])
    return export.response(wb, filename)
