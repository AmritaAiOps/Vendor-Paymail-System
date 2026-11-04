import contextlib
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import config
from app.auth import require_admin
from app.models import get_db
from app.schemas import RunNowOut
from app.sending import NotConfigured, run_due, scheduled_run, send_time


_running: BackgroundScheduler | None = None


def _trigger() -> CronTrigger:
    hour, minute = send_time()
    return CronTrigger(hour=hour, minute=minute, timezone=config.TIMEZONE)


def build_scheduler() -> BackgroundScheduler:
    """The daily T+2 job at send_time, Asia/Kolkata. Several app workers each run one; the claim step in
    run_due makes that safe."""
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(scheduled_run, _trigger(), id="t_plus_2_send", coalesce=True, max_instances=1, misfire_grace_time=3600)
    return scheduler


def reschedule() -> None:
    """Move the daily job to the current send_time (called after Settings saves it).
    ponytail: only this worker's job moves; with several workers the others keep the old time until restart."""
    if _running is not None:
        _running.reschedule_job("t_plus_2_send", trigger=_trigger())


@contextlib.asynccontextmanager
async def lifespan(app):
    global _running
    _running = build_scheduler()
    _running.start()
    yield
    _running.shutdown(wait=False)
    _running = None


router = APIRouter(prefix="/scheduler", tags=["scheduler"], lifespan=lifespan)


@router.post("/run-now", response_model=RunNowOut, dependencies=[Depends(require_admin)])
def run_now(ignore_date: bool = False, db: Session = Depends(get_db)):
    """Run the T+2 job now. ignore_date=true also sends emails whose send date is still in the future (for testing).
    503 if real sending is on but SMTP isn't configured (nothing is touched)."""
    try:
        return RunNowOut(**run_due(db, date.max if ignore_date else None))
    except NotConfigured as e:
        raise HTTPException(503, str(e))
