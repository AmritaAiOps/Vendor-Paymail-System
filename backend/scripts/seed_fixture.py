"""Load the three-row fixture into the dev DB so Person B can build emails and screens without the engine.

Run from backend/ after `alembic upgrade head`:  .venv/Scripts/python -m scripts.seed_fixture
Seeds one batch, the vendor, the consolidated + bank rows the results point at, and the three results.
"""
import sys

from sqlalchemy import select

from app.contract import BatchStatus
from app.models import BankTransaction, ConsolidatedEntry, ReconciliationResult, SessionLocal, UploadBatch, Vendor
from tests.fixtures import three_row_example as fx


def seed(db) -> int:
    """Insert the fixture, commit, return the batch id. ValueError if the vendor is already there."""
    if db.scalar(select(Vendor).where(Vendor.party_name == fx.VENDOR["party_name"])):
        raise ValueError("already seeded: delete dev.db and run `alembic upgrade head` to start over")
    batch = UploadBatch(status=BatchStatus.RECONCILED, **fx.FILE_NAMES)
    vendor = Vendor(is_email_valid=True, **fx.VENDOR)
    db.add_all([batch, vendor])
    db.flush()
    for e in fx.CONSOLIDATED_ENTRIES:
        entry = ConsolidatedEntry(batch_id=batch.id, **e)
        bank = BankTransaction(batch_id=batch.id, **fx.BANK_TRANSACTIONS[e["utr"]])
        db.add_all([entry, bank])
        db.flush()
        db.add(ReconciliationResult(consolidated_entry_id=entry.id, bank_txn_id=bank.id, vendor_id=vendor.id,
                                    **fx.EXPECTED_RESULTS[e["invoice_no"]]))
    db.commit()
    return batch.id


if __name__ == "__main__":
    with SessionLocal() as db:
        try:
            print(f"Seeded batch {seed(db)}: 1 vendor, 3 reconciliation results")
        except ValueError as err:
            sys.exit(str(err))
