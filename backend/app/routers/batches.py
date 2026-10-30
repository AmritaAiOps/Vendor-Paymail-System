from fastapi import APIRouter, UploadFile

from app.routers import stub

router = APIRouter(prefix="/batches", tags=["batches"])

EXAMPLE = {
    "id": 1,
    "created_at": "2026-10-30T10:00:00",
    "status": "uploaded",
    "source_files": {"consolidated": "c.xlsx", "bank": "b.xls", "gdn": "g.xlsx", "tds": "t.xlsx", "vendors": "v.xlsx"},
    "error": None,
}


@router.post("", status_code=201)
def upload(consolidated: UploadFile, bank: UploadFile, gdn: UploadFile, tds: UploadFile, vendors: UploadFile):
    return stub(EXAMPLE, 201)


@router.get("")
def list_batches():
    return stub([EXAMPLE])


@router.get("/{batch_id}")
def get_batch(batch_id: int):
    return stub({**EXAMPLE, "id": batch_id, "counts": {"pending": 0, "ready": 0, "exception": 0, "manual_review": 0, "emailed": 0}})
