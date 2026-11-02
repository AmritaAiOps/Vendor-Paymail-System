from fastapi import APIRouter

from app.routers import STUB
from app.schemas import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut, dependencies=[STUB])
def me():
    return MeOut(email="stub-admin@example.com", is_admin=True)
