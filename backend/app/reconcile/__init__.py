"""Reconciliation. Owner: Person A."""
from sqlalchemy.orm import Session


def resolve_review(db: Session, result_id: int, reason: str, who: str) -> None:
    """Set the reason on a MANUAL_REVIEW result, move it to DEDUCTION, audit, commit. ValueError if not MANUAL_REVIEW."""
    # STUB(contract): Person A replaces this.
    raise NotImplementedError("resolve_review")
