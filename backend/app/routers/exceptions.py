from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("")
def exceptions():
    return stub([])
