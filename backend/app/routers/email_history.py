import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import config
from app.contract import HistoryStatus
from app.history import xlsx
from app.models import EmailHistory, get_db
from app.schemas import HistoryOut, RowCountOut

router = APIRouter(prefix="/email-history", tags=["email-history"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _contains(col, text: str):
    return func.lower(col).contains(text.lower(), autoescape=True)


@router.get("", response_model=list[HistoryOut])
def history(response: Response, date_from: date | None = None, date_to: date | None = None,
            vendor: str | None = Query(None, max_length=255), status: HistoryStatus | None = None,
            q: str | None = Query(None, max_length=128, description="part of a UTR or invoice no"),
            limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """Newest first. Headers: X-Total-Count (rows matching every filter) and X-Status-Counts (JSON, per status,
    for the date / vendor / search filters only, so the counts stay visible while a status is selected)."""
    # shortcut: the date range compares the stored logged_at as is (server clock), not IST; fix if the DB isn't on IST
    where = []
    if date_from:
        where.append(EmailHistory.logged_at >= datetime.combine(date_from, time.min))
    if date_to:
        where.append(EmailHistory.logged_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if vendor:
        where.append(_contains(EmailHistory.vendor_name, vendor))
    if q:
        where.append(or_(_contains(EmailHistory.utr, q), _contains(EmailHistory.invoice_no, q)))
    found = dict(db.execute(select(EmailHistory.status, func.count()).where(*where).group_by(EmailHistory.status)).all())
    counts = {s.value: found.get(s, 0) for s in HistoryStatus}
    response.headers["X-Total-Count"] = str(counts[status.value] if status else sum(counts.values()))
    response.headers["X-Status-Counts"] = json.dumps(counts)
    rows = select(EmailHistory).where(*where)
    if status:
        rows = rows.where(EmailHistory.status == status)
    rows = rows.order_by(EmailHistory.logged_at.desc(), EmailHistory.id.desc()).limit(limit).offset(offset)
    return [HistoryOut.model_validate(h, from_attributes=True) for h in db.scalars(rows)]


@router.get("/export.xlsx")  # declared before /{id} so the literal path wins
def export(db: Session = Depends(get_db)):
    """The same file the sender keeps up to date. Catches it up first (never raises), so it is current."""
    xlsx.append_new_rows(db)
    path = Path(config.HISTORY_XLSX_PATH)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise HTTPException(404, "No history yet")
    except OSError as err:  # open in Excel on Windows
        raise HTTPException(503, f"Could not read the history file (is it open in Excel?): {err}")
    return Response(data, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="email_history.xlsx"'})


@router.post("/rebuild-xlsx", response_model=RowCountOut)
def rebuild_xlsx(db: Session = Depends(get_db)):
    # No admin check: the contract has no login or roles yet. Add one here if that changes.
    try:
        return RowCountOut(rows=xlsx.rebuild(db))
    except Exception as err:  # locked by another writer, open in Excel, disk error
        raise HTTPException(503, f"Could not write the history file (is it open in Excel?): {err}")


@router.get("/{id}", response_model=HistoryOut)
def history_row(id: int, db: Session = Depends(get_db)):
    h = db.get(EmailHistory, id)
    if h is None:
        raise HTTPException(404, "Not found")
    return HistoryOut.model_validate(h, from_attributes=True)
