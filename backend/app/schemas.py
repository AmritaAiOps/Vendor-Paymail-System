"""API request/response models: the contract in code. Shared, frozen at foundation-v1.
Money is Decimal, which Pydantic serialises to a JSON string ("120000.00")."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.contract import BatchStatus, ExceptionType, HistoryStatus, QueueStatus, ResultStatus


class HealthOut(BaseModel):
    status: str


class BatchOut(BaseModel):
    id: int
    uploaded_at: datetime
    consolidated_file: str
    bank_file: str
    gdn_file: str
    tds_file: str
    vendors_file: str
    status: BatchStatus
    error_message: str | None


class RowIssue(BaseModel):
    sheet: str
    row: int  # Excel row number
    message: str
    rejected: bool  # False = row kept, but flagged (e.g. invalid email dropped)


class FileReport(BaseModel):
    file_name: str
    rows_read: int  # non-blank data rows
    rows_kept: int
    rows_skipped: int  # dropped on purpose: bank credits, totals rows, duplicate vendors
    rows_rejected: int
    issues: list[RowIssue]


class BatchSummary(BaseModel):
    batch: BatchOut
    counts: dict[ResultStatus, int]  # every ResultStatus key present, 0 if none
    files: dict[str, FileReport] = {}  # keyed consolidated | bank | gdn | tds | vendors


class ResultOut(BaseModel):
    id: int
    batch_id: int
    vendor_id: int | None  # matched vendor; null for VENDOR_NOT_FOUND
    vendor_name: str
    invoice_no: str
    utr: str | None
    invoice_value: Decimal
    payment_date: date | None
    amount_paid: Decimal | None
    tds_amount: Decimal | None
    invoice_deduction: Decimal | None
    reason: str | None
    status: ResultStatus
    exception_type: ExceptionType | None
    send_on_date: date | None  # email_queue.send_on_date once queued


class RunNowOut(BaseModel):
    sent: int
    failed: int
    dry_run: int
    not_sent: int


class QueueItemOut(BaseModel):
    id: int
    vendor_id: int
    vendor_name: str
    to_email: str | None
    send_on_date: date
    status: QueueStatus
    sent_at: datetime | None
    subject: str | None
    invoice_count: int


class EmailPreview(BaseModel):
    subject: str
    html: str
    text: str


class HistoryOut(BaseModel):
    id: int
    logged_at: datetime
    batch_id: int | None
    vendor_name: str
    to_email: str | None
    subject: str | None
    invoice_no: str | None
    utr: str | None
    invoice_amount: Decimal | None
    payment_date: date | None
    amount_paid: Decimal | None
    tds_amount: Decimal | None
    invoice_deduction: Decimal | None
    reason: str | None
    status: HistoryStatus
    not_sent_reason: ExceptionType | None
    scheduled_send_date: date | None
    sent_at: datetime | None
    error_message: str | None
    email_queue_id: int | None


class RowCountOut(BaseModel):
    rows: int


class ScheduledOut(BaseModel):
    scheduled: int  # DRAFT emails moved to PENDING by Send all


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class GdnUploadOut(BaseModel):
    rows_read: int
    requeued: int


class VendorEmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=500)  # one address or a comma-separated list


class VendorOut(BaseModel):
    id: int
    party_name: str
    email: str | None
    is_email_valid: bool


class SettingsModel(BaseModel):
    """GET and PUT /api/settings body."""
    dry_run: bool
    send_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # HH:MM, IST
    signature: str = Field(max_length=500)  # sign-off under the email table; may span lines
    # email wording; defaults keep an older client's PUT (without these) valid
    email_subject: str = Field("Payment Details – {vendor} – {company}", max_length=200)
    email_intro: str = Field("Please find below the payment details for your invoices.", max_length=500)
    email_outro: str = Field("Please review and reply with any questions.", max_length=500)
    email_closing: str = Field("Yours faithfully,", max_length=100)
    email_company: str = Field("Sudhamayi Enterprises Pvt. Ltd.", max_length=200)


class SmtpSettingsIn(BaseModel):
    """PUT /api/settings/smtp. password: None or "" keeps the saved one (it is never sent back)."""
    host: str = Field(max_length=255)
    port: int = Field(ge=1, le=65535)
    user: str = Field(max_length=255)
    password: str | None = Field(None, max_length=255)
    from_email: str = Field(max_length=255)
    from_name: str = Field(max_length=255)
    starttls: bool


class SmtpSettingsOut(BaseModel):
    """GET/PUT /api/settings/smtp. locked = fields set in the server environment (they win; edit them there)."""
    host: str
    port: int
    user: str
    password_set: bool
    from_email: str
    from_name: str
    starttls: bool
    locked: list[str]


class MeOut(BaseModel):
    """GET /api/auth/me, and what app.auth.require_viewer / require_admin return."""
    email: str
    is_admin: bool


class VendorListStatus(BaseModel):
    """GET /api/vendor-list. exists=False until the first list is uploaded (version 0); runs are blocked until then."""
    exists: bool
    version: int
    file_name: str | None
    updated_at: datetime | None
    updated_by: str | None
    total: int


class VendorRow(BaseModel):
    """One line of the stored list. id=None for a row that is new in the edit table."""
    id: int | None = None
    party_name: str = Field(max_length=255)
    email: str | None = Field(None, max_length=500)  # one address or a comma-separated list


class VendorListOut(BaseModel):
    version: int
    vendors: list[VendorRow]


class VendorListIn(BaseModel):
    """PUT /api/vendor-list/vendors: the whole edit table, and the version it was loaded at."""
    base_version: int = Field(ge=0)
    vendors: list[VendorRow]


class VendorChange(BaseModel):
    party_name: str
    old_party_name: str
    old_email: str | None
    new_email: str | None


class VendorPreviewOut(BaseModel):
    """POST /api/vendor-list/preview: what the file would change. Nothing is stored."""
    file_name: str
    total: int  # vendors in the file
    base_version: int  # send this back with the confirmation
    new: list[VendorRow]
    removed: list[VendorRow]
    changed: list[VendorChange]
    unchanged: int
    issues: list[RowIssue]


class VendorSaveOut(BaseModel):
    status: VendorListStatus
    requeued: int  # earlier exceptions that this change unblocked and queued for email


class VendorHistoryOut(BaseModel):
    id: int
    version: int
    logged_at: datetime
    user: str
    action: str  # UPLOAD | EDIT | EMAIL_FIX
    file_name: str | None
    vendor_count: int
    added: int
    removed: int
    changed: int
    details: dict | None


class PendingMailOut(BaseModel):
    """One scheduled (PENDING) email the daily job has not sent yet."""
    id: int
    vendor_id: int
    vendor_name: str
    invoice_count: int
    send_on_date: date
    scheduled_at: datetime  # send_on_date at the daily send time, with the IST offset
    missing_utr_count: int  # this vendor's invoices that have no UTR: they are not in the email (see PendingSummaryOut)


class PendingSummaryOut(BaseModel):
    """GET /api/email-queue/pending-summary: what the exit pop-up and the missing-UTR notification show."""
    total: int
    missing_utr_mails: int  # pending emails whose vendor has at least one invoice with no UTR
    missing_utr_invoices: int  # all invoices with no UTR (latest result per invoice), whether or not the vendor has a mail
    items: list[PendingMailOut]


class SendAllIn(BaseModel):
    ids: list[int] = Field(min_length=1)  # the emails the user was shown
    include_missing_utr: bool = False  # False: emails flagged with a missing UTR are held and stay scheduled


class SendAllOut(BaseModel):
    sent: int
    failed: int
    dry_run: int
    not_sent: int
    held: int  # flagged missing-UTR emails left scheduled
    already_done: int  # sent or being sent by someone else meanwhile
