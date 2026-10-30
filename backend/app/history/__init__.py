"""Email attempt history: DB rows + append-only Excel. Owner: Person B."""
from sqlalchemy.orm import Session

from app.contract import AttemptRecord


def record_attempt(db: Session, record: AttemptRecord) -> None:
    """Insert one email_history row per record.rows entry, commit, then append the same rows to the Excel file."""
    # STUB(contract): Person B replaces this.
    raise NotImplementedError("record_attempt")
