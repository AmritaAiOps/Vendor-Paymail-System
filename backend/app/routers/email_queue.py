from datetime import date

from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/email-queue", tags=["email-queue"])


@router.get("")
def queue(on: date | None = None):
    return stub([])
