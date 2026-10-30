from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/email-history", tags=["email-history"])


@router.get("")
def history():
    return stub([])


@router.get("/export")
def export():
    return stub({"detail": "stub"}, 501)
