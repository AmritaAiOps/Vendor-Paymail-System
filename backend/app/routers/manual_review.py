from fastapi import APIRouter, UploadFile

from app.routers import STUB, canned_results
from app.schemas import GdnUploadOut, ReasonIn, ResultOut

router = APIRouter(prefix="/manual-review", tags=["manual-review"])


@router.get("", response_model=list[ResultOut], dependencies=[STUB])
def manual_review():
    return []  # the fixture has no manual-review rows


@router.put("/{result_id}/reason", response_model=ResultOut, dependencies=[STUB])
def set_reason(result_id: int, body: ReasonIn):
    return canned_results()[-1].model_copy(update={"id": result_id, "reason": body.reason})


@router.post("/gdn-upload", response_model=GdnUploadOut, dependencies=[STUB])
def gdn_upload(file: UploadFile):
    return GdnUploadOut(rows_read=1, requeued=0)
