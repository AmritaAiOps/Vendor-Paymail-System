from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("")
def vendors():
    return stub([])
