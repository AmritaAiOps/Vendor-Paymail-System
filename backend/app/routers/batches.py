import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.contract import ResultStatus
from app.ingest import FILE_KINDS, FileError, ingest_batch
from app.ingest.clean import clean_str
from app.models import ConsolidatedEntry, ReconciliationResult, UploadBatch, get_db
from app.routers import STUB, canned_batch, canned_results
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


@router.get("/{id}/summary", response_model=BatchSummary)
def summary(id: int, db: Session = Depends(get_db)):
    batch = db.get(UploadBatch, id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    counts = {s: 0 for s in ResultStatus}
    counts.update(db.execute(
        select(ReconciliationResult.status, func.count())
        .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
        .where(ConsolidatedEntry.batch_id == id)
        .group_by(ReconciliationResult.status)).all())
    return BatchSummary(batch=BatchOut.model_validate(batch, from_attributes=True), counts=counts,
                        files=batch.ingest_report or {})


@router.post("/{id}/reconcile", response_model=BatchSummary, dependencies=[STUB])
def reconcile(id: int):
    counts = {s: 0 for s in ResultStatus}
    for r in canned_results():
        counts[r.status] += 1
    return BatchSummary(batch=canned_batch().model_copy(update={"id": id}), counts=counts)


@router.get("/{id}/results", response_model=list[ResultOut], dependencies=[STUB])
def results(id: int):
    return canned_results()
