from fastapi import APIRouter

from app.routers import STUB, stub_xlsx
from app.schemas import ResultOut

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("", response_model=list[ResultOut], dependencies=[STUB])
def exceptions():
    return []  # the fixture has no exceptions


@router.get("/export.xlsx")
def export():
    return stub_xlsx("exceptions.xlsx")
