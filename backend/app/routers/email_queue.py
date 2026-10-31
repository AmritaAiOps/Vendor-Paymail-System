from fastapi import APIRouter

from app.contract import QueueStatus
from app.routers import STUB, canned_queue
from app.schemas import EmailPreview, QueueItemOut

router = APIRouter(prefix="/email-queue", tags=["email-queue"])


@router.get("", response_model=list[QueueItemOut], dependencies=[STUB])
def queue(batch_id: int | None = None, status: QueueStatus | None = None):
    return [q for q in canned_queue() if status is None or q.status == status]


@router.get("/{id}/preview", response_model=EmailPreview, dependencies=[STUB])
def preview(id: int):
    return EmailPreview(subject="Payment advice (stub)", html="<p>stub</p>", text="stub")
