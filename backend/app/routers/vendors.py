import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import reconcile
from app.history.audit import log_change
from app.models import Vendor, get_db
from app.schemas import VendorEmailIn, VendorOut

router = APIRouter(prefix="/vendors", tags=["vendors"])
_ADDRESS = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


def _parse(text: str) -> tuple[list[str], list[str]]:
    """(valid, invalid) addresses from a comma- or semicolon-separated list. Nothing is guessed or repaired."""
    valid, bad, seen = [], [], set()
    for part in re.split(r"[,;]", text):
        part = part.strip()
        if not part:
            continue
        if not _ADDRESS.fullmatch(part):
            bad.append(part)
        elif part.casefold() not in seen:
            seen.add(part.casefold())
            valid.append(part)
    return valid, bad


@router.put("/{id}/email", response_model=VendorOut)
def set_email(id: int, body: VendorEmailIn, request: Request, db: Session = Depends(get_db)):
    vendor = db.get(Vendor, id)
    if vendor is None:
        raise HTTPException(404, "Vendor not found")
    valid, bad = _parse(body.email)
    if bad or not valid:
        raise HTTPException(422, f"Not a valid email address: {', '.join(bad) or body.email}")
    old = vendor.email
    vendor.email, vendor.is_email_valid = ", ".join(valid), True  # the only two columns B may write
    log_change(db, request, f"vendor {id} ({vendor.party_name}): email changed", old, vendor.email)
    db.commit()
    try:
        reconcile.requeue_vendor_exceptions(db, id)  # queues this vendor's exception rows that now pass
    except Exception as err:
        raise HTTPException(500, f"The email was saved, but re-checking this vendor's exceptions failed: {err}")
    return VendorOut.model_validate(vendor, from_attributes=True)
