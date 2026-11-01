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
    signature: str = Field(max_length=500)  # sign-off under the email table
