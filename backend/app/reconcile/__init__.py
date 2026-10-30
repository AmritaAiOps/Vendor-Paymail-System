"""Reconciliation. Owner: Person A."""
from sqlalchemy.orm import Session


def requeue_after_reason(session: Session, result_id: int, reason: str) -> None:
    """Set the reason on a MANUAL_REVIEW result, move it to DEDUCTION, audit, and queue it via
    email_builder.build_queue(result_ids=[result_id]). ValueError if the result is not MANUAL_REVIEW."""
    # STUB(contract): Person A replaces this. Do-nothing until then.
    return None


def requeue_vendor_exceptions(session: Session, vendor_id: int) -> int:
    """Re-check this vendor's VENDOR_NOT_FOUND / INVALID_EMAIL results (e.g. after an email fix) and queue
    the ones that now pass. Returns how many were queued."""
    # STUB(contract): Person A replaces this. Do-nothing until then.
    return 0
