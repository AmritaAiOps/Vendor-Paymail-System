import io
import os
import zipfile
from typing import Annotated

import msoffcrypto
import openpyxl
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.contract import ResultStatus
from app import vendor_list
from app.ingest import BATCH_KINDS, FILE_KINDS, DuplicateUpload, FileError, NoVendorList, attach_bank, detect_kind, ingest_batch
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


# The real file layouts (reference files/3): every column in order, with one made-up row. Values left out stay blank.
_N = "Sample Vendor Pvt Ltd"
_UTR = "UTIBR52026080112345"
_SAMPLE = {
    "consolidated": ("Sl NO:|Date of Entry|recordType|codTranId|brnCode|remitAccountType|remitAccountNo|remitterName|chqNo|remitAmount|"
                     "benefIfscCode|benefAccountType|benefAccountNo|benefName|origDetail1|Narration 1 |Narration 2- Invoice No|Narration 3- PO No|"
                     "Narration4 - PO Dt|GRN NO:|Cheque Number|Cheque Date|Cheque Amount|Invoice Amount|Debit Note|Diff|Transaction Date|UTR NO:",
                     ["116_SEPL_2026-27_PHY", "2026-08-05", "196", "11", "026005300009051", "", "504563", "Sudhamayi Enterprises Pvt Ltd",
                      "", 117000, "UTIB0000001", "11", "917020012345678", _N, "Axis Bank", "Phy Invoice", "INV-1001", "SE/PH/2026-27/77",
                      "2026-07-20", "SE/PH/GRN/26/5", "504563", "2026-08-05", 117000, 118000, 0, 1000, "2026-08-05", _UTR]),
    "bank": ("TransactionDate|ValueDate|Description|CreditDebitFlag|AmountInAccountCurrency|RunningTotal|TaskLiteral|ChequeNumber|"
             "OriginatingBranch|TxnClickDisplay",
             ["05/08/2026", "05/08/2026", f"NEFT DR-{_UTR}-{_N.upper()}-UTIB0000001-INV-1001", "D", 117000, 40811733.2, "MSD",
              "000000504563", "996", ""]),  # the UTR is read from the description
    "gdn": ("Date|Particulars|Voucher Type|Voucher No.|Voucher Ref. No.|Voucher Ref. Date|GSTIN/UIN|Narration|Gross Total|"
            "Purchase PHA Local - GST 05%|Input CGST|Input SGST|Purchase Invoice Rounding Off",
            ["2026-08-03", _N, "Debit Note", "GDN/001", "INV-1001", "2026-07-20", "29ABCDE1234F1Z5",
             "GDN return deduction against invoice INV-1001: short supply", 1000, 952.38, 23.81, 23.81, 0]),
    "tds": ("S.NO:|FY|Qtr|Month|PARTY NAME|PAN OF DEDUCTEE|HEAD OF EXPENSE|TDS SECTION CODE|NATURE OF PAYMENT|Narration|Division|"
            "Journal voucher No|Purchase  voucher Date|Inv No|Inv Date|INVOICE Taxable VALUE|TDS Rate|TDS |TDS |Total TDS|"
            "DATE OF DEDUCTION OF TDS|TDS CHEQUE NO:|TDS CHEQUE DATE|Cheque Amount|BANK NAME|BSR NO|Challan Sr no|Challan Date|"
            "Challan Amount|Challan Date|Due Date|No of Days Delay|No Of mth delay|Interest @ 1% for delay|Interest Amt|Remarks|"
            "Service tax registration No|Certificate received|Challan Status (whether soft copy received)|Challan|Certificate Number|"
            "TDS Sl No: PHA|Journal Entry StatusY/N",
            [1, "2026-27", "Q1", "2026-08-05", _N, "ABCDE1234F", "", "", "", "", "Pharmacy", "", "2026-08-05", "INV-1001",
             "2026-07-20", 1000000, 0.001, 1000, 1000, 1000]),
    "vendors": ("S.No|Vendor Name|Mode of Business|State|GSTIN/UIN|Contact Person Name|Contact NO.|Email ID|Contact Person Name.2|"
                "Contact NO. 2|Email ID- Contact 2|Status (MSME)",
                [1, _N, "Vendor", "Delhi", "29ABCDE1234F1Z5", "A. Kumar", "9999999999", "accounts@samplevendor.com", "NA", "NA", "NA", ""]),
}


@router.get("/sample/{kind}.xlsx")
def sample(kind: str):
    """The expected layout of one upload file: the real column headers, in order, and one made-up row."""
    if kind not in _SAMPLE:
        raise HTTPException(404, f"Unknown file kind {kind}")
    headers, row = _SAMPLE[kind]
    wb = openpyxl.Workbook()
    wb.active.append(headers.split("|"))
    wb.active.append(row)
    out = io.BytesIO()
    wb.save(out)
    return StreamingResponse(io.BytesIO(out.getvalue()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="sample-{kind}.xlsx"'})


@router.post("/detect", response_model=dict[str, str | None])
def detect(files: list[UploadFile]):
    """Which upload slot each file belongs to, by its column headers: {file name: consolidated|bank|gdn|tds|vendors|null}.
    null = can't tell (protected, unreadable or ambiguous). Nothing is stored."""
    out = {}
    for f in files[:len(FILE_KINDS)]:
        checked = _check_upload("", f)
        out[f.filename or ""] = None if isinstance(checked, dict) else detect_kind(checked[1])
    return out


@router.post("", status_code=201, response_model=BatchOut)
def upload(consolidated: UploadFile, gdn: UploadFile, tds: UploadFile, bank: UploadFile | None = None,
           consolidated_password: _Password = None, bank_password: _Password = None, gdn_password: _Password = None,
           tds_password: _Password = None, db: Session = Depends(get_db)):
    """The per-run files (the bank statement may be left out if it hasn't arrived: add it later with POST /{id}/bank); the vendors list is not part of the upload, it is the stored one (/api/vendor-list).
    422 detail = [{"file": kind, "message": ...}] covering every problem in every file; nothing is stored.
    A protected file without its <kind>_password (or with a wrong one) adds "password_required": true.
    409 if files with exactly the same rows were uploaded before against the same vendors list (the message names that
    batch); 409 if no vendors list is stored yet (upload one first)."""
    checked = {k: _check_upload(k, u, p) for k, u, p in zip(
        BATCH_KINDS, (consolidated, bank, gdn, tds),
        (consolidated_password, bank_password, gdn_password, tds_password)) if u is not None}
    problems = [c for c in checked.values() if isinstance(c, dict)]
    if not problems:
        try:
            return BatchOut.model_validate(ingest_batch(db, checked), from_attributes=True)
        except FileError as e:
            problems = e.problems
        except NoVendorList as e:
            raise HTTPException(409, str(e))
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


@router.post("/{id}/bank", response_model=BatchSummary)
def add_bank(id: int, bank: UploadFile, bank_password: _Password = None, db: Session = Depends(get_db)):
    """Attach the bank statement to a batch uploaded without one, then call POST /{id}/reconcile. 409 if it already has
    one; 422 detail like upload; 404 if no batch."""
    _batch(db, id)
    checked = _check_upload("bank", bank, bank_password)
    if isinstance(checked, dict):
        raise HTTPException(422, [checked])
    try:
        attach_bank(db, id, *checked)
    except FileError as e:
        raise HTTPException(422, e.problems)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return summary(id, db)


@router.post("/{id}/reconcile", response_model=BatchSummary)
def reconcile(id: int, db: Session = Depends(get_db)):
    """Reconcile every invoice of the batch (re-runnable) against the stored vendors list, queue the emails, return the new counts."""
    if not _batch(db, id).bank_file:
        raise HTTPException(409, "This batch has no bank statement yet. Add it first (POST /api/batches/{id}/bank).")
    if vendor_list.current(db) is None:
        raise HTTPException(409, str(NoVendorList()))
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
