"""Append a "who changed what" row to audit_log. There are no users (see CONTRACT.md), so "who" is the caller's address."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def log_change(db: Session, request: Request, what: str, old: str | None, new: str | None) -> None:
    """Adds the row; the caller commits. shortcut: client IP is the only identity there is, replace with the user once a login exists."""
    who = request.client.host if request.client else "unknown"
    db.add(AuditLog(what=f"{what} (from {who})", old_value=old, new_value=new))
