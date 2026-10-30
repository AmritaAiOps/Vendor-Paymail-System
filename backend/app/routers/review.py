from fastapi import APIRouter
from pydantic import BaseModel

from app.routers import stub

router = APIRouter(prefix="/review", tags=["review"])


class Resolve(BaseModel):
    reason: str


@router.get("")
def review_list():
    return stub([])


@router.post("/{transaction_id}")
def resolve(transaction_id: int, body: Resolve):
    return stub({"id": transaction_id, "status": "ready"})
