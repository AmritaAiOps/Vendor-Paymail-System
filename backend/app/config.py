"""Environment config + the app_settings store. Owner: Person A. Names are part of the contract; B reads, never writes."""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
HISTORY_XLSX_PATH = os.environ.get("HISTORY_XLSX_PATH", "./data/email_history.xlsx")
TIMEZONE = "Asia/Kolkata"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))  # per uploaded file

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Sudhamayi Enterprises Pvt. Ltd.")
SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").strip().lower() not in ("false", "0", "no")
# When set, every email goes to this inbox instead of the vendor (testing only; the send still counts as SENT)
TEST_RECIPIENT = os.environ.get("TEST_RECIPIENT", "").strip()


# The only keys the app_settings store accepts, with their defaults. Unknown keys are rejected so the
# settings API can never read or write secrets from the environment.
SETTINGS = {"dry_run": "true", "send_time": "10:00", "signature": "[Name, designation]"}


def get_setting(name: str) -> str:
    """Env var NAME (upper-case) first, then the app_settings row, then the default. KeyError for unknown names."""
    default = SETTINGS[name]
    if (env := os.environ.get(name.upper())) is not None:
        return env
    from app.models import AppSetting, SessionLocal  # models imports this module for DATABASE_URL

    with SessionLocal() as db:
        row = db.get(AppSetting, name)
        return row.value if row else default


def set_setting(name: str, value: str) -> None:
    """Upsert the app_settings row and append to audit_log, in one commit. An env var of the same name still wins on read."""
    if name not in SETTINGS:
        raise KeyError(name)
    from app.models import AppSetting, AuditLog, SessionLocal

    with SessionLocal() as db:
        row = db.get(AppSetting, name)
        old = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=name, value=value))
        db.add(AuditLog(what=f"setting:{name}", old_value=old, new_value=value))
        db.commit()
