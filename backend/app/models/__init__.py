"""DB engine, session and tables. Owner: Person A. Table and column names are contract."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app import config

engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db


Money = Numeric(14, 2)  # always Decimal in Python, never float


class Base(DeclarativeBase):
    pass


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[str] = mapped_column(String(20))  # uploaded | reconciled | failed
    source_files: Mapped[dict] = mapped_column(JSON)  # {"consolidated": "x.xlsx", ...}
    error: Mapped[str | None] = mapped_column(Text)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_key: Mapped[str] = mapped_column(String(255), unique=True)  # normalised name for matching
    email: Mapped[str | None] = mapped_column(Text)  # comma-separated, as loaded


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    utr: Mapped[str | None] = mapped_column(String(64), unique=True)  # null only for utr_missing
    vendor_name: Mapped[str] = mapped_column(String(255))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    invoice_no: Mapped[str] = mapped_column(String(128))
    po_no: Mapped[str | None] = mapped_column(String(128))
    grn_no: Mapped[str | None] = mapped_column(String(128))
    invoice_amount: Mapped[Decimal] = mapped_column(Money)
    cheque_amount: Mapped[Decimal] = mapped_column(Money)
    debit_note: Mapped[Decimal | None] = mapped_column(Money)
    diff: Mapped[Decimal | None] = mapped_column(Money)
    transaction_date: Mapped[date | None]
    payment_date: Mapped[date | None]  # bank value date
    amount_paid: Mapped[Decimal | None] = mapped_column(Money)  # bank debit
    tds_amount: Mapped[Decimal | None] = mapped_column(Money)
    invoice_deduction: Mapped[Decimal | None] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None]  # payment_date + 2 days
    status: Mapped[str] = mapped_column(String(20), index=True)  # contract.TxnStatus
    exception_code: Mapped[str | None] = mapped_column(String(32))  # contract.ExceptionCode
    status_detail: Mapped[str | None] = mapped_column(Text)


class EmailAttempt(Base):
    __tablename__ = "email_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    outcome: Mapped[str] = mapped_column(String(20), index=True)  # contract.Outcome
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"))
    vendor_name: Mapped[str] = mapped_column(String(255))
    to_email: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None]
    subject: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    exception_code: Mapped[str | None] = mapped_column(String(32))


class EmailAttemptItem(Base):
    __tablename__ = "email_attempt_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("email_attempts.id"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    utr: Mapped[str | None] = mapped_column(String(64))


class SentUtr(Base):
    """A row here means the UTR was emailed. The PK is the never-twice guarantee."""
    __tablename__ = "sent_utrs"
    utr: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("email_attempts.id"))
    sent_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
