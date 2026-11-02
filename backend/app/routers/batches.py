import io
import os
import zipfile
from typing import Annotated

import msoffcrypto
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.contract import ResultStatus
from app.ingest import FILE_KINDS, DuplicateUpload, FileError, ingest_batch
from app.ingest.clean import clean_str
from app.models import ConsolidatedEntry, ReconciliationResult, UploadBatch, get_db
from app.reconcile import reconcile_batch
from app.reports.results import results_count, results_out
from app.schemas import BatchOut, BatchSummary, ResultOut

router = APIRouter(prefix="/batches", tags=["batches"])

_MAGIC = {".xlsx": b"PK\x03\x04", ".xls": b"\xd0\xcf\x11\xe0"}  # zip / OLE2 signatures
# zip-bomb guard: an .xlsx may unpack to at most 50x the upload limit. The Aug-Sep reference files unpack 4-12x.
_UNZIP_RATIO = 50
_Password = Annotated[str | None, Form(max_length=255)]  # optional, one per file: <kind>_password


def _unzipped_size(data: bytes) -> int:
    """Total uncompressed size an .xlsx claims. 0 if it isn't a readable zip: the parser reports that later."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile:
        return 0


def _decrypt(data: bytes, password: str | None) -> bytes | str:
    """The workbook's bytes, decrypted in memory if it is password-protected; a problem message if that fails.
    The password is only used here: never stored or logged."""
    try:
        office = msoffcrypto.OfficeFile(io.BytesIO(data))
        if not office.is_encrypted():
            return data
    except Exception:  # not an Office container msoffcrypto knows; the signature checks report it
        return data
    if not password:
        return "is password-protected; enter its password"
    out = io.BytesIO()
    try:
        office.load_key(password=password)
        office.decrypt(out)
    except msoffcrypto.exceptions.InvalidKeyError:
        return "password is wrong; enter it again"
    except Exception:
        return "is password-protected with an encryption this app can't open; upload an unprotected copy"
    return out.getvalue()


def _check_upload(kind: str, upload: UploadFile, password: str | None = None) -> tuple[str, bytes] | dict:
    """(file name, bytes) if the upload looks like a real Excel file within the size limit, else a problem dict.
    A protected file is decrypted with password; without the right one the problem has password_required."""
    name = (clean_str(upload.filename) or "").replace("\\", "/").rsplit("/", 1)[-1]  # some browsers send a full path
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    name = stem[:255 - len(ext)] + ext  # fits the String(255) column; Postgres rejects a longer one with a 500
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = upload.file.read(limit + 1)
    problem = None
    if ext not in _MAGIC:
        problem = f"{name or 'file'} is not an Excel file (.xlsx or .xls)"
    elif len(data) > limit:
        problem = f"{name} is larger than {config.MAX_UPLOAD_MB} MB"
    elif not data:
        problem = f"{name} is empty"
    elif data.startswith(_MAGIC[".xls"]) and isinstance(data := _decrypt(data, password), str):
        return {"file": kind, "message": f"{name} {data}", "password_required": True}
    elif not data.startswith(_MAGIC[ext]):
        problem = f"{name} is not a valid {ext} file"
    elif ext == ".xlsx" and _unzipped_size(data) > _UNZIP_RATIO * limit:
        problem = f"{name} unpacks to more than {_UNZIP_RATIO * config.MAX_UPLOAD_MB} MB; it can't be a normal report"
    return {"file": kind, "message": problem} if problem else (name, data)


@router.post("", status_code=201, response_model=BatchOut)
def upload(consolidated: UploadFile, bank: UploadFile, gdn: UploadFile, tds: UploadFile, vendors: UploadFile,
           consolidated_password: _Password = None, bank_password: _Password = None, gdn_password: _Password = None,
           tds_password: _Password = None, vendors_password: _Password = None, db: Session = Depends(get_db)):
    """422 detail = [{"file": kind, "message": ...}] covering every problem in every file; nothing is stored.
    A protected file without its <kind>_password (or with a wrong one) adds "password_required": true.
    409 if files with exactly the same rows were uploaded before (the message names that batch)."""
    checked = {k: _check_upload(k, u, p) for k, u, p in zip(
        FILE_KINDS, (consolidated, bank, gdn, tds, vendors),
        (consolidated_password, bank_password, gdn_password, tds_password, vendors_password))}
    problems = [c for c in checked.values() if isinstance(c, dict)]
    if not problems:
        try:
            return BatchOut.model_validate(ingest_batch(db, checked), from_attributes=True)
        except FileError as e:
            problems = e.problems
        except DuplicateUpload as e:
            raise HTTPException(409, f"These files have exactly the same rows as batch {e.batch_id}. Open that batch instead.")
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
    where = [ConsolidatedEntry.batch_id == id]
    if status:
        where.append(ReconciliationResult.status == status)
    if vendor:
        where.append(func.lower(ConsolidatedEntry.vendor_name).contains(vendor.lower(), autoescape=True))
    response.headers["X-Total-Count"] = str(results_count(db, *where))
    return results_out(db, *where, limit=limit, offset=offset)
