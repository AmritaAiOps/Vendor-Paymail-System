"""Vendor email rendering. Owner: Person B."""
from datetime import date

from app.contract import EmailRow


def build_email(vendor_name: str, due_date: date, rows: list[EmailRow]) -> tuple[str, str]:
    """Return (subject, html_body) for one vendor's email. Empty cells for None values."""
    # STUB(contract): Person B replaces this.
    raise NotImplementedError("build_email")
