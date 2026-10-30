from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/reconcile", tags=["reconcile"])


@router.post("/{batch_id}")
def run(batch_id: int):
    return stub({"batch_id": batch_id, "ready": 0, "exception": 0, "manual_review": 0, "skipped_duplicate": 0})
