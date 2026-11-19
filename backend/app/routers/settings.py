
from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.auth import require_admin
from app.email_builder import sample_email
from app.routers.scheduler import reschedule
from app.schemas import EmailPreview, MeOut, SettingsModel, SmtpSettingsOut
from app.sending import dry_run
from app.sending.smtp import SendError, deliver

router = APIRouter(prefix="/settings", tags=["settings"])

# Only the SettingsModel keys ever leave this router: config.get_setting refuses any other name, so no secret can.


_WORDING = ("email_subject", "email_intro", "email_outro", "email_closing", "email_company")


def _current() -> SettingsModel:
    return SettingsModel(
        dry_run=dry_run(), send_time=config.get_setting("send_time"), signature=config.get_setting("signature"),
        **{k: config.get_setting(k) for k in _WORDING})


def _as_stored(s: SettingsModel) -> dict[str, str]:
    return {"dry_run": "true" if s.dry_run else "false", "send_time": s.send_time, "signature": s.signature,
            **{k: getattr(s, k) for k in _WORDING}}


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
    signature = "\n".join(line.strip() for line in body.signature.strip().splitlines())  # several lines are fine
    if not signature:
        raise HTTPException(422, "Signature can't be empty")
    wording = {k: getattr(body, k).strip() for k in _WORDING}
    if any(c in v for v in wording.values() for c in "\r\n\t"):
        raise HTTPException(422, "Email wording must be one line each")
    if not (wording["email_subject"] and wording["email_closing"] and wording["email_company"]):
        raise HTTPException(422, "Subject, closing and company name can't be empty")
    new = _as_stored(body.model_copy(update={"signature": signature, **wording}))
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


# --- Email server (SMTP): read-only, set in the server environment (SMTP_* in .env). Admin only. ---
@router.get("/smtp", response_model=SmtpSettingsOut, dependencies=[Depends(require_admin)])
def get_smtp():
    s = config.smtp()
    return SmtpSettingsOut(host=s["host"], port=s["port"], user=s["user"], password_set=bool(s["password"]),
                           from_email=s["from"], from_name=s["from_name"], starttls=s["starttls"])


@router.post("/smtp/test")
def test_smtp(me: MeOut = Depends(require_admin)):
    """Sends one test email to the signed-in admin with the SMTP_* settings. 422 with the server's reason if it fails."""
    s = config.smtp()
    if not (s["host"] and s["from"]):
        raise HTTPException(422, "Set SMTP_HOST and SMTP_FROM in the server .env first")
    try:
        deliver([me.email], "Vendor Paymail: test email",
                "<p>This is a test email from Vendor Paymail. The mail server settings work.</p>",
                "This is a test email from Vendor Paymail. The mail server settings work.")
    except SendError as e:
        raise HTTPException(422, str(e))
    return {"sent_to": me.email}
