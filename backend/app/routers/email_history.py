from fastapi import APIRouter, HTTPException

from app.routers import STUB, canned_history, stub_xlsx
from app.schemas import HistoryOut, RowCountOut

router = APIRouter(prefix="/email-history", tags=["email-history"])


@router.get("", response_model=list[HistoryOut], dependencies=[STUB])
def history():
    return canned_history()


@router.get("/export.xlsx")  # declared before /{id} so the literal path wins
def export():
    return stub_xlsx("email_history.xlsx")


@router.post("/rebuild-xlsx", response_model=RowCountOut, dependencies=[STUB])
def rebuild_xlsx():
    return RowCountOut(rows=len(canned_history()))


@router.get("/{id}", response_model=HistoryOut, dependencies=[STUB])
def history_row(id: int):
    for h in canned_history():
        if h.id == id:
            return h
    raise HTTPException(404, "Not found")
