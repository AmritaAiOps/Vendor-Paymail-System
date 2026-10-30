from fastapi import APIRouter

from app.routers import STUB
from app.schemas import RunNowOut

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/run-now", response_model=RunNowOut, dependencies=[STUB])
def run_now():
    return RunNowOut(sent=0, failed=0, dry_run=3, not_sent=0)
