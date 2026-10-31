"""Append-only Excel copy of email_history at config.HISTORY_XLSX_PATH. Owner: Person B."""
from sqlalchemy.orm import Session


def append_new_rows(session: Session) -> int:
    """Append email_history rows not yet in the Excel file. Returns how many were appended."""
    # STUB(contract): Person B replaces this. Do-nothing until then.
    return 0


def rebuild(session: Session) -> int:
    """Rewrite the Excel file from the whole email_history table. Returns the row count."""
    # STUB(contract): Person B replaces this. Do-nothing until then.
    return 0
