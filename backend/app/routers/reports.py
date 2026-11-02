from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.email_builder.proforma import proforma_xlsx
from app.models import ConsolidatedEntry, get_db
from app.reports.export import response
from app.reports.results import results_out, results_xlsx
from app.routers.batches import _batch

router = APIRouter(prefix="/batches", tags=["reports"])


@router.get("/{id}/proforma.xlsx")
def proforma(id: int, db: Session = Depends(get_db)):
    _batch(db, id)
    return response(proforma_xlsx(db, id), f"proforma_batch_{id}.xlsx")


@router.get("/{id}/report.xlsx")
def report(id: int, db: Session = Depends(get_db)):
    """Every reconciliation result of the batch, whatever its status."""
    _batch(db, id)
    return results_xlsx(results_out(db, ConsolidatedEntry.batch_id == id), "Reconciliation", f"report_batch_{id}.xlsx")
