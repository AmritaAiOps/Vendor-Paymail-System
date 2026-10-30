from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
def summary():
    return stub({})
