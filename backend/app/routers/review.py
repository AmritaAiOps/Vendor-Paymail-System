from fastapi import APIRouter
from pydantic import BaseModel

from app.routers import stub

router = APIRouter(prefix="/review", tags=["review"])


class Resolve(BaseModel):
    reason: str


@router.get("")
def review_list():
    return stub([])


@router.post("/{result_id}")
def resolve(result_id: int, body: Resolve):
    return stub({"id": result_id, "status": "DEDUCTION"})
