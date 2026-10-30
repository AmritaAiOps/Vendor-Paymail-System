"""Shared types between Person A and Person B. Frozen at foundation-v1; change only via docs/CONTRACT.md."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class TxnStatus(StrEnum):
    PENDING = "pending"              # ingested, not reconciled yet
    READY = "ready"                  # reconciled, waits for due_date
    EXCEPTION = "exception"          # no email; see exception_code
    MANUAL_REVIEW = "manual_review"  # deduction > 0 with no reason
    EMAILED = "emailed"


class ExceptionCode(StrEnum):
    UTR_MISSING = "utr_missing"            # no UTR in the consolidated row
    UTR_NOT_IN_BANK = "utr_not_in_bank"
    VENDOR_NOT_FOUND = "vendor_not_found"
    INVALID_EMAIL = "invalid_email"
    REASON_MISSING = "reason_missing"      # goes with status manual_review


class Outcome(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    EXCEPTION = "exception"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class EmailRow:
    """One table row in the vendor email, columns in the contract order."""
    invoice_no: str
    invoice_amount: Decimal
    utr: str
    payment_date: date
    amount_paid: Decimal
    tds_amount: Decimal | None
    invoice_deduction: Decimal | None
    reason: str | None


@dataclass(frozen=True)
class VendorGroup:
    """All of one vendor's transactions due on one day = one email."""
    vendor_id: int
    vendor_name: str
    to_email: str
    due_date: date
    transaction_ids: list[int]
    rows: list[EmailRow]


@dataclass(frozen=True)
class AttemptRecord:
    """Everything history.record_attempt needs. One per attempt, sent or not."""
    outcome: Outcome
    vendor_name: str
    due_date: date | None
    transaction_ids: list[int]
    utrs: list[str]
    vendor_id: int | None = None
    to_email: str | None = None
    subject: str | None = None
    body_html: str | None = None
    error: str | None = None
    exception_code: ExceptionCode | None = None
