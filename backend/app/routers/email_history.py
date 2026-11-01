from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.history import xlsx
from app.models import get_db
from app.routers import STUB, canned_history, stub_xlsx
from app.schemas import HistoryOut, RowCountOut

router = APIRouter(prefix="/email-history", tags=["email-history"])


@router.get("", response_model=list[HistoryOut], dependencies=[STUB])
def history():
    return canned_history()


@router.get("/export.xlsx")  # declared before /{id} so the literal path wins
def export():
    return stub_xlsx("email_history.xlsx")


@router.post("/rebuild-xlsx", response_model=RowCountOut)
def rebuild_xlsx(db: Session = Depends(get_db)):
    # No admin check: the contract has no login or roles yet. Add one here if that changes.
    try:
        return RowCountOut(rows=xlsx.rebuild(db))
    except Exception as err:  # locked by another writer, open in Excel, disk error
        raise HTTPException(503, f"Could not write the history file (is it open in Excel?): {err}")


@router.get("/{id}", response_model=HistoryOut, dependencies=[STUB])
def history_row(id: int):
    for h in canned_history():
        if h.id == id:
            return h
    raise HTTPException(404, "Not found")
