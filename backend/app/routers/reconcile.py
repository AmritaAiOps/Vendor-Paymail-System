from fastapi import APIRouter

from app.routers import stub
from app.routers.batches import COUNTS

router = APIRouter(prefix="/reconcile", tags=["reconcile"])


@router.post("/{batch_id}")
def run(batch_id: int):
    return stub({"batch_id": batch_id, "counts": COUNTS})
