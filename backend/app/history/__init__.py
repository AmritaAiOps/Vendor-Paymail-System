"""Email attempt history: DB rows + append-only Excel. Owner: Person B."""
from sqlalchemy.orm import Session

from app.contract import AttemptRecord


def record_attempt(db: Session, record: AttemptRecord) -> int:
    """Insert email_attempts + email_attempt_items, commit, append to the Excel file. Returns attempt id."""
    # STUB(contract): Person B replaces this.
    raise NotImplementedError("record_attempt")
