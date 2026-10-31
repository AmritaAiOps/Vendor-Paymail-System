from fastapi import APIRouter

from app.routers import stub_xlsx

router = APIRouter(prefix="/batches", tags=["reports"])


@router.get("/{id}/proforma.xlsx")
def proforma(id: int):
    return stub_xlsx(f"proforma_batch_{id}.xlsx")


@router.get("/{id}/report.xlsx")
def report(id: int):
    return stub_xlsx(f"report_batch_{id}.xlsx")
