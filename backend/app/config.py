"""Environment config + the app_settings store. Owner: Person A. Names are part of the contract; B reads, never writes."""
import os

from sqlalchemy.orm import Session

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
HISTORY_XLSX_PATH = os.environ.get("HISTORY_XLSX_PATH", "./data/email_history.xlsx")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
TIMEZONE = "Asia/Kolkata"

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    from app.models import AppSetting  # models imports this module for DATABASE_URL

    row = db.get(AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str, updated_by: str) -> None:
    """Upsert one setting, audit the change, commit."""
    from app.models import AppSetting, AuditLog

    row = db.get(AppSetting, key)
    old = row.value if row else None
    if row:
        row.value, row.updated_by = value, updated_by
    else:
        db.add(AppSetting(key=key, value=value, updated_by=updated_by))
    db.add(AuditLog(who=updated_by, what=f"setting:{key}", old_value=old, new_value=value))
    db.commit()
