from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.email_builder.proforma import proforma_xlsx
from app.models import ConsolidatedEntry, UploadBatch, get_db
from app.reports.export import XLSX
from app.reports.results import results_out, results_xlsx

router = APIRouter(prefix="/batches", tags=["reports"])


@router.get("/{id}/proforma.xlsx")
def proforma(id: int, db: Session = Depends(get_db)):
    if db.get(UploadBatch, id) is None:
        raise HTTPException(404, "Batch not found")
    return Response(proforma_xlsx(db, id), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="proforma_batch_{id}.xlsx"'})


@router.get("/{id}/report.xlsx")
def report(id: int, db: Session = Depends(get_db)):
    """Every reconciliation result of the batch, whatever its status."""
    if db.get(UploadBatch, id) is None:
        raise HTTPException(404, "Batch not found")
    return results_xlsx(results_out(db, ConsolidatedEntry.batch_id == id), "Reconciliation", f"report_batch_{id}.xlsx")
