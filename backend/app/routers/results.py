from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.contract import ResultStatus
from app.models import ConsolidatedEntry, ReconciliationResult, get_db
from app.reports.results import latest_only, results_count, results_out, results_xlsx
from app.schemas import ResultOut

router = APIRouter(prefix="/results", tags=["results"])


def _filters(status: ResultStatus | None, vendor: str | None, q: str | None, date_from: date | None, date_to: date | None):
    """Shared by the list and the export, so a download holds exactly the rows on screen."""
    where = [latest_only()]  # a newer upload of the same vendor + invoice replaces the older result
    if status:
        where.append(ReconciliationResult.status == status)
    if vendor:
        where.append(func.lower(ConsolidatedEntry.vendor_name).contains(vendor.lower(), autoescape=True))
    if q:
        like = q.lower()
        where.append(or_(func.lower(ConsolidatedEntry.invoice_no).contains(like, autoescape=True),
                         func.lower(func.coalesce(ConsolidatedEntry.utr, "")).contains(like, autoescape=True)))
    if date_from:
        where.append(ReconciliationResult.payment_date >= date_from)
    if date_to:
        where.append(ReconciliationResult.payment_date <= date_to)
    return where


@router.get("", response_model=list[ResultOut])
def results(response: Response, status: ResultStatus | None = None, vendor: str | None = Query(None, max_length=255),
            q: str | None = Query(None, max_length=255, description="part of the invoice number or UTR"),
            date_from: date | None = None, date_to: date | None = None,
            limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """Results from every upload, filtered by payment date, vendor, status or invoice/UTR. Total before paging: X-Total-Count."""
    where = _filters(status, vendor, q, date_from, date_to)
    response.headers["X-Total-Count"] = str(results_count(db, *where))
    return results_out(db, *where, limit=limit, offset=offset)


@router.get("/export.xlsx")  # declared before any /{id} so the literal path wins
def export(status: ResultStatus | None = None, vendor: str | None = Query(None, max_length=255),
           q: str | None = Query(None, max_length=255), date_from: date | None = None, date_to: date | None = None,
           db: Session = Depends(get_db)):
    return results_xlsx(results_out(db, *_filters(status, vendor, q, date_from, date_to)), "Results", "results.xlsx")
