from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.contract import ResultStatus
from app.models import ReconciliationResult, get_db
from app.reports.results import results_out, results_xlsx
from app.schemas import ResultOut

router = APIRouter(prefix="/exceptions", tags=["exceptions"])
_is_exception = ReconciliationResult.status == ResultStatus.EXCEPTION  # no email goes out for these


@router.get("", response_model=list[ResultOut])
def exceptions(db: Session = Depends(get_db)):
    return results_out(db, _is_exception)


@router.get("/export.xlsx")  # declared before any /{id} so the literal path wins
def export(db: Session = Depends(get_db)):
    return results_xlsx(results_out(db, _is_exception), "Exceptions", "exceptions.xlsx")
