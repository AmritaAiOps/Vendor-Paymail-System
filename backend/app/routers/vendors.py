from fastapi import APIRouter

from app.routers import STUB, canned_vendor
from app.schemas import VendorEmailIn, VendorOut

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.put("/{id}/email", response_model=VendorOut, dependencies=[STUB])
def set_email(id: int, body: VendorEmailIn):
    return canned_vendor().model_copy(update={"id": id, "email": body.email})
