"""Email queue and rendering. Owner: Person B."""
from sqlalchemy.orm import Session


def build_queue(session: Session, batch_id: int | None = None, result_ids: list[int] | None = None) -> list[int]:
    """Create email_queue + email_items rows (one queue row per vendor + send date, one item per UTR)
    for sendable results of a batch, or for the given results. Skips UTRs already in email_items.
    Returns the new email_queue ids."""
    # STUB(contract): Person B replaces this. Do-nothing until then.
    return []


def render_email(session: Session, queue_id: int) -> tuple[str, str, str]:
    """Return (subject, html, text) for one email_queue row. Table columns in contract order; empty cells stay empty."""
    # STUB(contract): Person B replaces this.
    return ("Payment advice (stub)", "<p>stub</p>", "stub")
