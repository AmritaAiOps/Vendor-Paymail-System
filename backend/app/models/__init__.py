"""DB engine, session and tables. Owner: Person A. Table and column names are contract."""
from datetime import date, datetime
from decimal import Decimal

import sqlite3

from sqlalchemy import JSON, Enum, ForeignKey, MetaData, Numeric, String, Text, create_engine, event, false, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app import config
from app.contract import BatchStatus, ExceptionType, HistoryStatus, QueueStatus, ResultStatus


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked, per connection; Postgres always enforces them. Same rules in dev,
    tests and production. (alembic/env.py turns them off again for migrations, which rebuild tables.)"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


Money = Numeric(14, 2)  # always Decimal in Python, never float


def Choice(e):
    # CHECK constraint instead of a native PG enum: same on SQLite and Postgres, no ALTER TYPE later
    return Enum(e, native_enum=False, create_constraint=True, length=20)


class Base(DeclarativeBase):
    # Alembic's recommended naming convention, so constraints can be altered later
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class UploadBatch(Base):
    __tablename__ = "upload_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())
    consolidated_file: Mapped[str] = mapped_column(String(255))
    bank_file: Mapped[str] = mapped_column(String(255))
    gdn_file: Mapped[str] = mapped_column(String(255))
    tds_file: Mapped[str] = mapped_column(String(255))
    vendors_file: Mapped[str] = mapped_column(String(255))
    status: Mapped[BatchStatus] = mapped_column(Choice(BatchStatus))
    error_message: Mapped[str | None] = mapped_column(Text)
    ingest_report: Mapped[dict | None] = mapped_column(JSON)  # per file: row counts + rejected rows and reasons


class ConsolidatedEntry(Base):
    __tablename__ = "consolidated_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)
    utr: Mapped[str | None] = mapped_column(String(64), index=True)  # 66 of 2,209 Aug–Sep rows have none
    invoice_no: Mapped[str] = mapped_column(String(128))
    po_no: Mapped[str | None] = mapped_column(String(128))
    grn_no: Mapped[str | None] = mapped_column(String(128))
    invoice_amount: Mapped[Decimal] = mapped_column(Money)
    cheque_amount: Mapped[Decimal] = mapped_column(Money)
    debit_note: Mapped[Decimal | None] = mapped_column(Money)
    diff: Mapped[Decimal | None] = mapped_column(Money)
    transaction_date: Mapped[date | None]


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    value_date: Mapped[date]
    utr: Mapped[str] = mapped_column(String(64), index=True)
    debit: Mapped[Decimal] = mapped_column(Money)
    description: Mapped[str | None] = mapped_column(Text)
    vendor_name: Mapped[str | None] = mapped_column(String(255), index=True)  # parsed from description
    ifsc: Mapped[str | None] = mapped_column(String(11))
    is_bounced: Mapped[bool] = mapped_column(default=False, server_default=false())  # a NEFT RETURN credit names this UTR
    bounce_note: Mapped[str | None] = mapped_column(Text)  # the return row's description, e.g. "PAYMENT STOPPED"


class GdnRecord(Base):
    __tablename__ = "gdn_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)  # Particulars
    invoice_no: Mapped[str | None] = mapped_column(String(128), index=True)  # Voucher Ref. No.
    voucher_no: Mapped[str | None] = mapped_column(String(64))
    gdn_date: Mapped[date | None]
    amount: Mapped[Decimal | None] = mapped_column(Money)  # Gross Total
    reason: Mapped[str | None] = mapped_column(Text)  # Narration


class TdsRecord(Base):
    __tablename__ = "tds_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_batches.id"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)  # PARTY NAME
    invoice_no: Mapped[str | None] = mapped_column(String(128), index=True)  # Inv No
    invoice_date: Mapped[date | None]
    tds_amount: Mapped[Decimal] = mapped_column(Money)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    party_name: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str | None] = mapped_column(Text)  # comma-separated
    is_email_valid: Mapped[bool] = mapped_column(default=False)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    consolidated_entry_id: Mapped[int] = mapped_column(ForeignKey("consolidated_entries.id"), unique=True)
    bank_txn_id: Mapped[int | None] = mapped_column(ForeignKey("bank_transactions.id"))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), index=True)  # matched by name_key
    invoice_value: Mapped[Decimal] = mapped_column(Money)
    payment_date: Mapped[date | None]  # bank value date
    amount_paid: Mapped[Decimal | None] = mapped_column(Money)  # bank debit
    tds_amount: Mapped[Decimal | None] = mapped_column(Money)
    invoice_deduction: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ResultStatus] = mapped_column(Choice(ResultStatus), index=True)
    exception_type: Mapped[ExceptionType | None] = mapped_column(Choice(ExceptionType))


class EmailQueue(Base):
    __tablename__ = "email_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    send_on_date: Mapped[date] = mapped_column(index=True)
    status: Mapped[QueueStatus] = mapped_column(Choice(QueueStatus), default=QueueStatus.PENDING)
    sent_at: Mapped[datetime | None]
    subject: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)


class EmailItem(Base):
    __tablename__ = "email_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_queue_id: Mapped[int] = mapped_column(ForeignKey("email_queue.id"), index=True)
    reconciliation_result_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_results.id"))
    utr: Mapped[str] = mapped_column(String(64), unique=True)  # the never-emailed-twice guarantee


class SendLog(Base):
    __tablename__ = "send_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_queue_id: Mapped[int] = mapped_column(ForeignKey("email_queue.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[HistoryStatus] = mapped_column(Choice(HistoryStatus))
    error_message: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    what: Mapped[str] = mapped_column(Text)
    logged_at: Mapped[datetime] = mapped_column(server_default=func.now())
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)


class EmailHistory(Base):
    """Append-only: a DB trigger (see the migration) rejects UPDATE and DELETE."""
    __tablename__ = "email_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(server_default=func.now())
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("upload_batches.id"))
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)
    to_email: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    invoice_no: Mapped[str | None] = mapped_column(String(128))
    utr: Mapped[str | None] = mapped_column(String(64), index=True)
    invoice_amount: Mapped[Decimal | None] = mapped_column(Money)
    payment_date: Mapped[date | None]
    amount_paid: Mapped[Decimal | None] = mapped_column(Money)
    tds_amount: Mapped[Decimal | None] = mapped_column(Money)
    invoice_deduction: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[HistoryStatus] = mapped_column(Choice(HistoryStatus), index=True)
    not_sent_reason: Mapped[ExceptionType | None] = mapped_column(Choice(ExceptionType))
    scheduled_send_date: Mapped[date | None]
    sent_at: Mapped[datetime | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    email_queue_id: Mapped[int | None] = mapped_column(ForeignKey("email_queue.id"))


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
