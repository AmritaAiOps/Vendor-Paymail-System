"""Environment config + the app_settings store. Owner: Person A. Names are part of the contract; B reads, never writes."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
HISTORY_XLSX_PATH = os.environ.get("HISTORY_XLSX_PATH", "./data/email_history.xlsx")
TIMEZONE = "Asia/Kolkata"


def now_ist() -> datetime:
    """Wall-clock time in India, without tzinfo: every stored timestamp (uploaded, sent, logged) is IST."""
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))  # per uploaded file; deploy/nginx.conf caps the body to match
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# SMTP: env var (e.g. SMTP_HOST) first, else the Settings page (app_settings), else these defaults. See smtp().
# When set, every email goes to this inbox instead of the vendor (testing only; the send still counts as SENT)
TEST_RECIPIENT = os.environ.get("TEST_RECIPIENT", "").strip()

# Firebase login (app.auth). Env only, never in app_settings. Empty project ID = every protected route answers 503.
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "").strip().lower().lstrip("@")
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


# The only keys the app_settings store accepts, with their defaults. Unknown keys are rejected so the
# settings API can never read or write other secrets from the environment.
SETTINGS = {"dry_run": "true", "send_time": "10:00", "signature": "[Name, designation]"}
# SMTP keys are stored the same way but read only through smtp(); smtp_password is never returned by the API
# or written to audit_log. ponytail: stored in plain text in app_settings; set SMTP_PASSWORD in env to keep it out of the DB.
SMTP_SETTINGS = {"smtp_host": "", "smtp_port": "587", "smtp_user": "", "smtp_password": "", "smtp_from": "",
                 "smtp_from_name": "Sudhamayi Enterprises Pvt. Ltd.", "smtp_starttls": "true"}


def env_value(name: str) -> str | None:
    """The env var NAME (upper-case), or None if unset or empty: an empty line in .env doesn't lock a setting."""
    return os.environ.get(name.upper()) or None


def _stored(name: str, default: str) -> str:
    if (env := env_value(name)) is not None:
        return env
    from app.models import AppSetting, SessionLocal  # models imports this module for DATABASE_URL

    with SessionLocal() as db:
        row = db.get(AppSetting, name)
        return row.value if row else default


def get_setting(name: str) -> str:
    """Env var NAME (upper-case) first, then the app_settings row, then the default. KeyError for unknown names."""
    return _stored(name, SETTINGS[name])


def smtp() -> dict:
    """The mail server settings in effect: host, port, user, password, from, from_name, starttls."""
    v = {k.removeprefix("smtp_"): _stored(k, d) for k, d in SMTP_SETTINGS.items()}
    try:
        v["port"] = int(v["port"])
    except ValueError:
        v["port"] = 587
    v["starttls"] = v["starttls"].strip().lower() not in ("false", "0", "no", "off")
    return v


def set_setting(name: str, value: str) -> None:
    """Upsert the app_settings row and append to audit_log, in one commit. An env var of the same name still wins on read."""
    if name not in SETTINGS and name not in SMTP_SETTINGS:
        raise KeyError(name)
    from app.models import AppSetting, AuditLog, SessionLocal

    hide = (lambda v: "(hidden)" if v else v) if name == "smtp_password" else (lambda v: v)
    with SessionLocal() as db:
        row = db.get(AppSetting, name)
        old = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=name, value=value))
        db.add(AuditLog(what=f"setting:{name}", old_value=hide(old), new_value=hide(value)))
        db.commit()
