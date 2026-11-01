"""Stub scaffolding shared by every router. Shared, frozen at foundation-v1.
A route is a stub while it has STUB in its dependencies; remove it when the route becomes real."""
import io
from datetime import datetime

from fastapi import Depends, Response
from openpyxl import Workbook

from app.schemas import BatchOut, HistoryOut, QueueItemOut, ResultOut, VendorOut
from tests.fixtures import three_row_example as fx  # shortcut: canned data only; goes when the last stub does


def _stub_header(response: Response) -> None:
    response.headers["X-Stub"] = "true"


STUB = Depends(_stub_header)


def stub_xlsx(filename: str) -> Response:
    """Canned .xlsx with the fixture's email table, for file endpoints."""
    wb = Workbook()
    wb.active.append(fx.EMAIL_HEADER)
    for row in fx.EMAIL_ROWS.values():
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), headers={"X-Stub": "true", "Content-Disposition": f'attachment; filename="{filename}"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def canned_batch() -> BatchOut:
    return BatchOut(id=1, uploaded_at=datetime(2025, 9, 16, 10, 0), status="RECONCILED",
                    error_message=None, **fx.FILE_NAMES)


def canned_results() -> list[ResultOut]:
    return [ResultOut(id=i, batch_id=1, vendor_id=1, vendor_name=e["vendor_name"], invoice_no=e["invoice_no"], utr=e["utr"],
                      send_on_date=fx.SEND_ON_DATES[fx.EXPECTED_RESULTS[e["invoice_no"]]["payment_date"]],
                      **fx.EXPECTED_RESULTS[e["invoice_no"]])
            for i, e in enumerate(fx.CONSOLIDATED_ENTRIES, 1)]


def canned_vendor() -> VendorOut:
    return VendorOut(id=1, is_email_valid=True, **fx.VENDOR)


def canned_queue() -> list[QueueItemOut]:
    return [QueueItemOut(id=i, vendor_id=1, vendor_name=fx.VENDOR["party_name"], to_email=fx.VENDOR["email"],
                         send_on_date=fx.SEND_ON_DATES[paid], status="PENDING", sent_at=None, subject=None,
                         invoice_count=len(invoices))
            for i, (paid, invoices) in enumerate(fx.EMAIL_GROUPS.items(), 1)]


def canned_history() -> list[HistoryOut]:
    return [HistoryOut(id=r.id, logged_at=datetime(2025, 9, 16, 10, 0), batch_id=1, vendor_name=r.vendor_name,
                       to_email=fx.VENDOR["email"], subject="Payment advice", invoice_no=r.invoice_no, utr=r.utr,
                       invoice_amount=r.invoice_value, payment_date=r.payment_date, amount_paid=r.amount_paid,
                       tds_amount=r.tds_amount, invoice_deduction=r.invoice_deduction, reason=r.reason,
                       status="DRY_RUN", not_sent_reason=None, scheduled_send_date=None, sent_at=None,
                       error_message=None, email_queue_id=1)
            for r in canned_results()]
