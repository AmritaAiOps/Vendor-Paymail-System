import re

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.auth import require_admin
from app.email_builder import sample_email
from app.routers.scheduler import reschedule
from app.schemas import EmailPreview, MeOut, SettingsModel, SmtpSettingsIn, SmtpSettingsOut
from app.sending import dry_run
from app.sending.smtp import SendError, deliver

router = APIRouter(prefix="/settings", tags=["settings"])

# Only the SettingsModel keys ever leave this router: config.get_setting refuses any other name, so no secret can.


def _current() -> SettingsModel:
    return SettingsModel(
        dry_run=dry_run(), send_time=config.get_setting("send_time"), signature=config.get_setting("signature"))


def _as_stored(s: SettingsModel) -> dict[str, str]:
    return {"dry_run": "true" if s.dry_run else "false", "send_time": s.send_time, "signature": s.signature}


@router.get("", response_model=SettingsModel)
def get_settings():
    return _current()


@router.get("/email-sample", response_model=EmailPreview)
def email_sample():
    """What a vendor email looks like: the real template with made-up rows and the current signature."""
    subject, html, text = sample_email()
    return EmailPreview(subject=subject, html=html, text=text)


@router.put("", response_model=SettingsModel, dependencies=[Depends(require_admin)])
def put_settings(body: SettingsModel):
    """send_time format and signature length are checked by SettingsModel (422). Only changed values are saved;
    config.set_setting writes one audit_log row per change. Admin only."""
    signature = body.signature.strip()
    if not signature:
        raise HTTPException(422, "Signature can't be empty")
    if any(c in signature for c in "\r\n\t"):
        raise HTTPException(422, "Signature must be one line")
    new = _as_stored(body.model_copy(update={"signature": signature}))
    old = _as_stored(_current())
    changed = {k: v for k, v in new.items() if v != old[k]}
    # Validate everything before writing anything: an env var wins on read, so saving it would silently do nothing
    if locked := [k.upper() for k in changed if config.env_value(k) is not None]:
        raise HTTPException(409, f"Set in the server environment, change it there: {', '.join(locked)}")
    for k, v in changed.items():
        config.set_setting(k, v)
    if "send_time" in changed:
        reschedule()
    return _current()


# --- Email server (SMTP). Admin only, both ways: the host and user aren't for every viewer. ---
_FIELDS = {"host": "smtp_host", "port": "smtp_port", "user": "smtp_user", "password": "smtp_password",
           "from_email": "smtp_from", "from_name": "smtp_from_name", "starttls": "smtp_starttls"}
_ADDRESS = re.compile(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+")


def _smtp_out() -> SmtpSettingsOut:
    s = config.smtp()
    return SmtpSettingsOut(host=s["host"], port=s["port"], user=s["user"], password_set=bool(s["password"]),
                           from_email=s["from"], from_name=s["from_name"], starttls=s["starttls"],
                           locked=[f for f, k in _FIELDS.items() if config.env_value(k) is not None])


@router.get("/smtp", response_model=SmtpSettingsOut, dependencies=[Depends(require_admin)])
def get_smtp():
    return _smtp_out()


@router.put("/smtp", response_model=SmtpSettingsOut, dependencies=[Depends(require_admin)])
def put_smtp(body: SmtpSettingsIn):
    """Saves the changed fields. 409 if a changed field is set in the server environment; nothing is saved then."""
    new = {"host": body.host.strip(), "port": str(body.port), "user": body.user.strip(), "from_email": body.from_email.strip(),
           "from_name": body.from_name.strip(), "starttls": "true" if body.starttls else "false"}
    if body.password:
        new["password"] = body.password
    if new["from_email"] and not _ADDRESS.fullmatch(new["from_email"]):
        raise HTTPException(422, f"Not a valid from address: {new['from_email']}")
    if any(c in v for v in new.values() for c in "\r\n"):
        raise HTTPException(422, "Values must be one line")
    current = config.smtp()
    now = {"host": current["host"], "port": str(current["port"]), "user": current["user"], "password": current["password"],
           "from_email": current["from"], "from_name": current["from_name"], "starttls": "true" if current["starttls"] else "false"}
    changed = {f: v for f, v in new.items() if v != now[f]}
    if locked := [_FIELDS[f].upper() for f in changed if config.env_value(_FIELDS[f]) is not None]:
        raise HTTPException(409, f"Set in the server environment, change it there: {', '.join(locked)}")
    for f, v in changed.items():
        config.set_setting(_FIELDS[f], v)
    return _smtp_out()


@router.post("/smtp/test")
def test_smtp(me: MeOut = Depends(require_admin)):
    """Sends one test email to the signed-in admin with the saved settings. 422 with the server's reason if it fails."""
    s = config.smtp()
    if not (s["host"] and s["from"]):
        raise HTTPException(422, "Set the host and the from address first")
    try:
        deliver([me.email], "Vendor Paymail: test email",
                "<p>This is a test email from Vendor Paymail. The mail server settings work.</p>",
                "This is a test email from Vendor Paymail. The mail server settings work.")
    except SendError as e:
        raise HTTPException(422, str(e))
    return {"sent_to": me.email}
