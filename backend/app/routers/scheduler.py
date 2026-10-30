from datetime import date

from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("")
def status():
    return stub({"next_run_at": "2026-10-31T10:00:00+05:30", "last_run_at": None, "dry_run": True})


@router.post("/run")
def run_now(on: date | None = None):
    return stub({"on": str(on or date.today()), "sent": 0, "failed": 0, "dry_run": 0, "skipped": 0})
