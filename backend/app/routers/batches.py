import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.contract import ResultStatus
from app.ingest import FILE_KINDS, FileError, ingest_batch
from app.ingest.clean import clean_str
from app.models import ConsolidatedEntry, ReconciliationResult, UploadBatch, get_db
from app.reconcile import reconcile_batch
from app.schemas import BatchOut, BatchSummary, ResultOut

router = APIRouter(prefix="/batches", tags=["batches"])

_MAGIC = {".xlsx": b"PK\x03\x04", ".xls": b"\xd0\xcf\x11\xe0"}  # zip / OLE2 signatures


def _check_upload(kind: str, upload: UploadFile) -> tuple[str, bytes] | dict:
    """(file name, bytes) if the upload looks like a real Excel file within the size limit, else a problem dict."""
    name = clean_str(upload.filename) or ""
    ext = os.path.splitext(name)[1].lower()
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = upload.file.read(limit + 1)
    problem = None
    if ext not in _MAGIC:
        problem = f"{name or 'file'} is not an Excel file (.xlsx or .xls)"
    elif len(data) > limit:
        problem = f"{name} is larger than {config.MAX_UPLOAD_MB} MB"
    elif not data:
        problem = f"{name} is empty"
    elif ext == ".xlsx" and data.startswith(_MAGIC[".xls"]):
        problem = f"{name} is password-protected; upload an unprotected copy"
    elif not data.startswith(_MAGIC[ext]):
        problem = f"{name} is not a valid {ext} file"
    return {"file": kind, "message": problem} if problem else (name, data)


@router.post("", status_code=201, response_model=BatchOut)
def upload(consolidated: UploadFile, bank: UploadFile, gdn: UploadFile, tds: UploadFile, vendors: UploadFile,
           db: Session = Depends(get_db)):
    """422 detail = [{"file": kind, "message": ...}] covering every problem in every file; nothing is stored."""
    checked = {k: _check_upload(k, u) for k, u in zip(FILE_KINDS, (consolidated, bank, gdn, tds, vendors))}
    problems = [c for c in checked.values() if isinstance(c, dict)]
    if not problems:
        try:
            return BatchOut.model_validate(ingest_batch(db, checked), from_attributes=True)
        except FileError as e:
            problems = e.problems
    raise HTTPException(422, problems)


def _batch(db: Session, id: int) -> UploadBatch:
    batch = db.get(UploadBatch, id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


@router.get("/{id}/summary", response_model=BatchSummary)
def summary(id: int, db: Session = Depends(get_db)):
    batch = _batch(db, id)
    counts = {s: 0 for s in ResultStatus}
    counts.update(db.execute(
        select(ReconciliationResult.status, func.count())
        .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
        .where(ConsolidatedEntry.batch_id == id)
        .group_by(ReconciliationResult.status)).all())
    return BatchSummary(batch=BatchOut.model_validate(batch, from_attributes=True), counts=counts,
                        files=batch.ingest_report or {})


@router.post("/{id}/reconcile", response_model=BatchSummary)
def reconcile(id: int, db: Session = Depends(get_db)):
    """Reconcile every invoice of the batch (re-runnable), queue the emails, return the new counts."""
    _batch(db, id)
    reconcile_batch(db, id)
    return summary(id, db)


@router.get("/{id}/results", response_model=list[ResultOut])
def results(id: int, response: Response, status: ResultStatus | None = None,
            vendor: str | None = Query(None, max_length=255, description="part of the vendor name, any case"),
            limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """One page of results in consolidated-report order. The total before paging is in the X-Total-Count header."""
    _batch(db, id)
    q = (select(ReconciliationResult, ConsolidatedEntry)
         .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
         .where(ConsolidatedEntry.batch_id == id))
    if status:
        q = q.where(ReconciliationResult.status == status)
    if vendor:
        q = q.where(func.lower(ConsolidatedEntry.vendor_name).contains(vendor.lower(), autoescape=True))
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(q.subquery())))
    return [ResultOut(id=r.id, batch_id=id, vendor_name=e.vendor_name, invoice_no=e.invoice_no, utr=e.utr,
                      invoice_value=r.invoice_value, payment_date=r.payment_date, amount_paid=r.amount_paid,
                      tds_amount=r.tds_amount, invoice_deduction=r.invoice_deduction, reason=r.reason,
                      status=r.status, exception_type=r.exception_type)
            for r, e in db.execute(q.order_by(ConsolidatedEntry.id).limit(limit).offset(offset))]
