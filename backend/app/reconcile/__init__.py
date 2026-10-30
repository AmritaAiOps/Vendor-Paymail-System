"""Reconciliation. Owner: Person A."""
from sqlalchemy.orm import Session


def resolve_review(db: Session, transaction_id: int, reason: str) -> None:
    """Set the reason on a manual_review transaction and move it to ready. Commits. ValueError if not in manual_review."""
    # STUB(contract): Person A replaces this.
    raise NotImplementedError("resolve_review")
