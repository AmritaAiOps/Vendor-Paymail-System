"""Shared types between Person A and Person B. Frozen at foundation-v1; change only via docs/CONTRACT.md."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class BatchStatus(StrEnum):
    UPLOADED = "UPLOADED"
    RECONCILED = "RECONCILED"
    FAILED = "FAILED"


class ResultStatus(StrEnum):
    PAID_IN_FULL = "PAID_IN_FULL"
    TDS_ONLY = "TDS_ONLY"
    DEDUCTION = "DEDUCTION"
    EXCEPTION = "EXCEPTION"          # no email; see exception_type
    MANUAL_REVIEW = "MANUAL_REVIEW"  # deduction > 0 with no reason


class ExceptionType(StrEnum):
    """Why a row gets no email. Also used as email_history.not_sent_reason."""
    UTR_NOT_FOUND = "UTR_NOT_FOUND"
    VENDOR_NOT_FOUND = "VENDOR_NOT_FOUND"
    INVALID_EMAIL = "INVALID_EMAIL"
    REASON_MISSING = "REASON_MISSING"  # goes with ResultStatus.MANUAL_REVIEW


class QueueStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class HistoryStatus(StrEnum):
    SENT = "SENT"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"
    NOT_SENT = "NOT_SENT"


@dataclass(frozen=True)
class EmailRow:
    """One invoice row, columns in the email's order. utr/payment_date/amount_paid are None only on NOT_SENT rows."""
    invoice_no: str
    invoice_amount: Decimal
    utr: str | None
    payment_date: date | None
    amount_paid: Decimal | None
    tds_amount: Decimal | None
    invoice_deduction: Decimal | None
    reason: str | None


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt, sent or not. history.record_attempt writes one email_history row per entry in rows."""
    status: HistoryStatus
    vendor_name: str
    rows: list[EmailRow]
    batch_id: int | None = None
    to_email: str | None = None
    subject: str | None = None
    not_sent_reason: ExceptionType | None = None
    scheduled_send_date: date | None = None
    sent_at: datetime | None = None
    error_message: str | None = None
    email_queue_id: int | None = None
