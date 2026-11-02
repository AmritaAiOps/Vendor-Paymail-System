import contextlib

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import config
from app.auth import require_admin
from app.models import get_db
from app.schemas import RunNowOut
from app.sending import NotConfigured, run_due, scheduled_run, send_time


def build_scheduler() -> BackgroundScheduler:
    """The daily T+2 job at send_time, Asia/Kolkata. Several app workers each run one; the claim step in
    run_due makes that safe. shortcut: send_time is read at startup, so changing it needs a restart."""
    hour, minute = send_time()
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(scheduled_run, CronTrigger(hour=hour, minute=minute, timezone=config.TIMEZONE),
                      id="t_plus_2_send", coalesce=True, max_instances=1, misfire_grace_time=3600)
    return scheduler


@contextlib.asynccontextmanager
async def lifespan(app):
    scheduler = build_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


router = APIRouter(prefix="/scheduler", tags=["scheduler"], lifespan=lifespan)


@router.post("/run-now", response_model=RunNowOut, dependencies=[Depends(require_admin)])
def run_now(db: Session = Depends(get_db)):
    """Run the T+2 job now. 503 if real sending is on but SMTP isn't configured (nothing is touched)."""
    try:
        return RunNowOut(**run_due(db))
    except NotConfigured as e:
        raise HTTPException(503, str(e))
