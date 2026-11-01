"""Reconciliation engine: every special case runs the real pipeline (upload -> ingest -> reconcile) on fixture rows."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ingest import ingest_batch
from app.models import BankTransaction, ConsolidatedEntry, EmailItem, EmailQueue, ReconciliationResult, Vendor
from app.reconcile import reconcile_batch
from app.sending import send_on_date
from tests.fixtures import special_cases as sc
from tests.fixtures import three_row_example as fx
from tests.util import files_from


@pytest.fixture
def queue_calls(monkeypatch):
    """build_queue is Person B's: record the calls instead of running the stub."""
    calls = []
    monkeypatch.setattr("app.reconcile.build_queue", lambda session, **kw: calls.append(kw) or [])
    return calls


def reconciled(db, fixture) -> dict:
    """Upload the fixture's five files, reconcile, return {(invoice no, utr): (result, entry)}."""
    batch = ingest_batch(db, files_from(fixture))
    reconcile_batch(db, batch.id)
    rows = db.execute(select(ReconciliationResult, ConsolidatedEntry)
                      .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id)
                      .where(ConsolidatedEntry.batch_id == batch.id))
    return {(e.invoice_no, e.utr): (r, e) for r, e in rows}


FIELDS = ("status", "exception_type", "tds_amount", "invoice_deduction", "reason")


def test_three_row_example(db, queue_calls):
    results = reconciled(db, fx)
    assert len(results) == 3
    for (invoice_no, _), (r, _) in results.items():
        expected = fx.EXPECTED_RESULTS[invoice_no]
        actual = {k: getattr(r, k) for k in expected}
        assert actual == expected, invoice_no
    assert len(queue_calls) == 1 and set(queue_calls[0]) == {"batch_id"}  # handed to Person B by contract name
    # the send date the email builder will use, from the bank value date
    assert {send_on_date(r.payment_date) for r, _ in results.values()} == set(fx.SEND_ON_DATES.values())


def test_special_cases(db, queue_calls):
    results = reconciled(db, sc)
    assert set(results) == set(sc.EXPECTED)
    wrong = {}
    for key, expected in sc.EXPECTED.items():
        actual = {k: getattr(results[key][0], k) for k in FIELDS}
        if actual != expected:
            wrong[key] = (actual, expected)
    assert not wrong, wrong


def test_amounts_and_payment_date_come_from_the_bank(db, queue_calls):
    results = reconciled(db, sc)
    r, e = results[("INV-S01", sc.utr(1))]
    assert (r.invoice_value, r.amount_paid, r.payment_date) == (Decimal("100000.00"), Decimal("94900.00"), sc.PAID_ON)
    r, _ = results[("INV-S09", sc.utr(9))]  # no bank row: nothing paid to show
    assert (r.amount_paid, r.payment_date, r.bank_txn_id) == (None, None, None)


def test_duplicate_amounts_stay_separate(db, queue_calls):
    results = reconciled(db, sc)
    a, b = results[("INV-S10", sc.utr(10))][0], results[("INV-S11", sc.utr(11))][0]
    assert a.bank_txn_id != b.bank_txn_id
    assert {db.get(BankTransaction, x.bank_txn_id).utr for x in (a, b)} == {sc.utr(10), sc.utr(11)}


def test_empty_means_null_and_deductions_carry_a_reason(db, queue_calls):
    results = {**reconciled(db, sc), **reconciled(db, fx)}
    for key, (r, _) in results.items():
        assert r.tds_amount is None or r.tds_amount > 0, key
        assert r.invoice_deduction is None or r.invoice_deduction > 0, key
        assert r.reason is None or r.reason.strip(), key
        if r.status == "DEDUCTION":
            assert r.invoice_deduction and r.reason, key
        if r.status in ("PAID_IN_FULL", "TDS_ONLY"):
            assert r.invoice_deduction is None and r.reason is None, key
        assert isinstance(r.invoice_value, Decimal) and (r.amount_paid is None or isinstance(r.amount_paid, Decimal))


def test_vendor_matched_by_name_variant_is_stored(db, queue_calls):
    r, _ = reconciled(db, sc)[("INV-S06", sc.utr(6))]  # "R.K PHARMA" vs vendor list "R.K. Pharma"
    assert r.vendor_id is not None


def test_rerun_recomputes_but_leaves_queued_results_alone(db, queue_calls):
    batch = ingest_batch(db, files_from(sc))
    reconcile_batch(db, batch.id)
    ids = lambda: {r.consolidated_entry_id: r for r in db.scalars(select(ReconciliationResult))}
    first = ids()
    queued, other = list(first.values())[:2]
    queue = EmailQueue(vendor_id=queued.vendor_id or db.scalar(select(Vendor.id)), send_on_date=date(2025, 9, 18))
    db.add(queue)
    db.flush()
    db.add(EmailItem(email_queue_id=queue.id, reconciliation_result_id=queued.id, utr="X"))
    queued.reason, other.reason = "edited after queueing", "stale"
    db.commit()

    reconcile_batch(db, batch.id)
    second = ids()
    assert len(second) == len(first) == len(sc.EXPECTED)  # no duplicates
    assert second[queued.consolidated_entry_id].reason == "edited after queueing"  # queued: untouched
    assert second[other.consolidated_entry_id].reason != "stale"  # not queued: recomputed
    assert len(queue_calls) == 2


def test_reconcile_and_results_endpoints(client, db, queue_calls):
    batch_id = ingest_batch(db, files_from(sc)).id
    r = client.post(f"/api/batches/{batch_id}/reconcile")
    assert r.status_code == 200 and "x-stub" not in r.headers
    counts = r.json()["counts"]
    assert counts == {"PAID_IN_FULL": 6, "TDS_ONLY": 2, "DEDUCTION": 3, "EXCEPTION": 6, "MANUAL_REVIEW": 7}
    assert r.json()["batch"]["status"] == "RECONCILED"

    queued = db.scalars(select(ReconciliationResult).where(ReconciliationResult.vendor_id.is_not(None))).first()
    queue = EmailQueue(vendor_id=queued.vendor_id, send_on_date=date(2025, 9, 18))
    db.add(queue)
    db.flush()
    db.add(EmailItem(email_queue_id=queue.id, reconciliation_result_id=queued.id, utr="X"))
    db.commit()

    r = client.get(f"/api/batches/{batch_id}/results")
    assert {x["id"]: x["send_on_date"] for x in r.json() if x["send_on_date"]} == {queued.id: "2025-09-18"}
    assert r.status_code == 200 and "x-stub" not in r.headers
    assert r.headers["x-total-count"] == "24" and len(r.json()) == 24
    s01 = next(x for x in r.json() if x["invoice_no"] == "INV-S01")
    assert (s01["tds_amount"], s01["invoice_deduction"], s01["amount_paid"]) == ("100.00", "5000.00", "94900.00")

    r = client.get(f"/api/batches/{batch_id}/results", params={"status": "EXCEPTION", "vendor": "sunrise"})
    assert {x["invoice_no"] for x in r.json()} == {"INV-S09", "INV-S12"}
    r = client.get(f"/api/batches/{batch_id}/results", params={"limit": 5, "offset": 20})
    assert len(r.json()) == 4 and r.headers["x-total-count"] == "24"
    r = client.get(f"/api/batches/{batch_id}/results", params={"vendor": "100%_"})  # wildcards are literal
    assert r.json() == []

    assert client.get(f"/api/batches/{batch_id}/results", params={"status": "NOPE"}).status_code == 422
    assert client.get(f"/api/batches/{batch_id}/results", params={"limit": 501}).status_code == 422
    assert client.post("/api/batches/999/reconcile").status_code == 404
    assert client.get("/api/batches/999/results").status_code == 404


def test_send_on_date_follows_payment_date():
    assert send_on_date(date(2025, 9, 12)) == date(2025, 9, 15)  # the three-row example's Friday payments
