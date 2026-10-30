"""Shared enums and types between Person A and Person B. Frozen at foundation-v1; change only via docs/CONTRACT.md."""
from dataclasses import dataclass
from datetime import date
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
    BOUNCED = "BOUNCED"  # the bank returned the payment (NEFT RETURN); shown highlighted


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
class GdnRow:
    """One parsed GDN Report row, as returned by ingest.load_gdn_file."""
    vendor_name: str
    invoice_no: str | None
    voucher_no: str | None
    gdn_date: date | None
    amount: Decimal | None
    reason: str | None
