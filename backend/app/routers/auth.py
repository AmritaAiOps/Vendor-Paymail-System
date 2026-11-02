from fastapi import APIRouter, Depends

from app.auth import require_viewer
from app.schemas import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
def me(user: MeOut = Depends(require_viewer)):  # same call as the router-level check, so FastAPI runs it once
    return user
