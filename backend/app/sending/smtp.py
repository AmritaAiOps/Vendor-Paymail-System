"""The one place that talks to the mail server. To move to SendGrid or SES, replace deliver() and keep its contract."""
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app import config


class SendError(Exception):
    """retry_safe=True: nothing reached the server, so trying again cannot double-send.
    retry_safe=False: refused, or it may have been delivered. Never retry those."""

    def __init__(self, message: str, retry_safe: bool):
        super().__init__(message)
        self.retry_safe = retry_safe


def deliver(to: list[str], subject: str, html: str, text: str) -> dict:
    """Send one email (plain text + HTML). Returns the addresses the server refused, if it accepted the others."""
    msg = EmailMessage()
    msg["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_FROM))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid()
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)  # shortcut: no implicit-TLS port 465; add SMTP_SSL if a provider needs it
        if config.SMTP_STARTTLS:
            smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
    except (OSError, smtplib.SMTPException) as e:
        raise SendError(f"could not connect to the mail server: {e}", retry_safe=True) from None
    try:
        return smtp.send_message(msg)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as e:
        raise SendError(f"refused by the mail server: {e}", retry_safe=False) from None
    except (OSError, smtplib.SMTPException) as e:
        raise SendError(f"failed during sending, may or may not have been delivered: {e}", retry_safe=False) from None
    finally:
        try:
            smtp.quit()
        except (OSError, smtplib.SMTPException):
            pass
