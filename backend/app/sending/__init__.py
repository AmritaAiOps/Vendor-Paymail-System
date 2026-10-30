"""T+2 sending. Owner: Person A."""
from datetime import date

from sqlalchemy.orm import Session

from app.contract import VendorGroup


def due_groups(db: Session, on: date) -> list[VendorGroup]:
    """Ready transactions with due_date <= on, not yet in sent_utrs, grouped one per vendor + due_date."""
    # STUB(contract): Person A replaces this.
    raise NotImplementedError("due_groups")
