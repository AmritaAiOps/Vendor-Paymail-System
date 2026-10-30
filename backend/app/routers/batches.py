from fastapi import APIRouter, UploadFile

from app.routers import stub

router = APIRouter(prefix="/batches", tags=["batches"])

EXAMPLE = {
    "id": 1,
    "uploaded_at": "2026-10-30T10:00:00",
    "uploaded_by": "admin",
    "consolidated_file": "c.xlsx",
    "bank_file": "b.xls",
    "gdn_file": "g.xlsx",
    "tds_file": "t.xlsx",
    "vendors_file": "v.xlsx",
    "status": "UPLOADED",
    "error_message": None,
}
COUNTS = {"PAID_IN_FULL": 0, "TDS_ONLY": 0, "DEDUCTION": 0, "EXCEPTION": 0, "MANUAL_REVIEW": 0}


@router.post("", status_code=201)
def upload(consolidated: UploadFile, bank: UploadFile, gdn: UploadFile, tds: UploadFile, vendors: UploadFile):
    return stub(EXAMPLE, 201)


@router.get("")
def list_batches():
    return stub([EXAMPLE])


@router.get("/{batch_id}")
def get_batch(batch_id: int):
    return stub({**EXAMPLE, "id": batch_id, "counts": COUNTS})
