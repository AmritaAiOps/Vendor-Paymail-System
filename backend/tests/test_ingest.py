import io
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from app.ingest import _parse, load_gdn_file
from app.ingest.clean import clean_str, name_key, normalize_utr, parse_amount, parse_date, split_emails
from app.models import ConsolidatedEntry, Vendor
from tests.fixtures import three_row_example as fx


def xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def upload_files(**override) -> dict:
    sources = {"consolidated": fx.CONSOLIDATED_SOURCE, "bank": fx.BANK_SOURCE, "gdn": fx.GDN_SOURCE,
               "tds": fx.TDS_SOURCE, "vendors": fx.VENDORS_SOURCE}
    files = {k: (f"{k}.xlsx", xlsx(rows)) for k, rows in sources.items()}
    return files | override


def test_parse_amount():
    assert parse_amount("5,45,060.00") == Decimal("545060.00")
    assert parse_amount("1,20,000.00") == Decimal("120000.00")
    assert parse_amount("4788") == Decimal("4788.00")
    assert parse_amount("1185.4999999999998") == Decimal("1185.50")  # float noise from Excel
    assert parse_amount("(2,334.00)") == Decimal("-2334.00")
    assert parse_amount("  ") is None
    for bad in ("abc", "NaN", "1,2,3.4.5"):
        with pytest.raises(ValueError):
            parse_amount(bad)


def test_parse_date():
    for raw in ("12-Sep-25", "12/09/2025", "2025-09-12 00:00:00", "45912", date(2025, 9, 12)):
        assert parse_date(raw) == date(2025, 9, 12), raw
    assert parse_date("01/08/2026") == date(2026, 8, 1)  # day first, never 8 Jan
    assert parse_date(None) is None
    with pytest.raises(ValueError):
        parse_date("31/02/2026")


def test_normalize_utr_and_hidden_chars():
    assert normalize_utr(" dlxbh25252000123​ ") == "DLXBH25252000123"
    assert normalize_utr("504411.0") == "504411"
    assert clean_str("GYAN DEEP ENTERPRISES_x000D_\n") == "GYAN DEEP ENTERPRISES"
    assert clean_str("ABC Pharma ﻿Distributors ") == "ABC Pharma Distributors"


def test_split_emails():
    assert split_emails("a@x.com; b@y.co.in / c@z.com>") == (["a@x.com", "b@y.co.in", "c@z.com"], [])
    assert split_emails("'Nitin Jain' <nitin.jain@alcon.com>") == (["nitin.jain@alcon.com"], [])
    assert split_emails("Ashwani Sharma' rbminca_del@concordbiotech.com") == (["rbminca_del@concordbiotech.com"], [])
    assert split_emails("not-an-email") == ([], ["not-an-email"])


def test_name_key_matches_spelling_variants():
    assert name_key("R.K PHARMA") == name_key("R.K. Pharma") == name_key(" r k  pharma ")
    assert name_key("A.C SURGIPHARMA PVT. LTD") == name_key("A.C Surgipharma Private Limited")
    assert name_key("6Ipain Healthcare Private Limited{6Ipnhpl}") == name_key("6IPAIN HEALTHCARE PRIVATE LIMITED")
    assert name_key("B J MADAN & CO") == name_key("B.J. Madan and Company")
    assert name_key("R.K PHARMA") != name_key("R.S PHARMA")


def test_vendors_contact_2_is_mailed_and_variants_dedupe():
    rows = [{"Vendor\nName": "R.K PHARMA", "Email ID": "a@rk.in", "Email ID- Contact 2": "b@rk.in; a@rk.in"},
            {"Vendor\nName": "R.K. Pharma", "Email ID": "c@rk.in", "Email ID- Contact 2": None},
            {"Vendor\nName": "Harkrishan Medicals", "Email ID": "h@hm.in", "Email ID- Contact 2": "harkrishan,medicals@x.com"}]
    vendors, report = _parse("vendors", xlsx(rows), "v.xlsx")
    assert [(v["party_name"], v["email"]) for v in vendors] == [("R.K PHARMA", "a@rk.in, b@rk.in"), ("Harkrishan Medicals", "h@hm.in")]
    assert report["rows_skipped"] == 1 and "contact 2 email ignored" in report["issues"][0]["message"]


def test_bank_return_marks_payment_bounced():
    bounce = {**fx.BANK_SOURCE[0], "Description": "NEFT RETURN-PAYMENT STOPPED-ABC PHARMA DISTRIBUTORS-DLXBH25252000188",
              "Ref / Cheque No": "INDBN52025091508202154", "Credit": "5,25,060.00", "Debit": "0.00"}
    stray = {**bounce, "Description": "NEFT RETURN-INCORRECT ACCOUNT NUMBER-X-DLXBH99999999999"}
    rows, report = _parse("bank", xlsx([*fx.BANK_SOURCE, bounce, stray]), "b.xlsx")
    assert [(r["utr"], r["is_bounced"]) for r in rows] == [
        ("DLXBH25252000123", False), ("DLXBH25252000150", False), ("DLXBH25252000188", True)]
    assert rows[2]["bounce_note"] == bounce["Description"]
    assert [i["message"][:22] for i in report["issues"]] == ["payment DLXBH252520001", "return of a payment no"]


def test_vendors_deduped_keep_valid_email():
    rows = [{"Vendor\nName": "ABC Pharma Distributors", "Email ID": "broken"}, *fx.VENDORS_SOURCE]
    vendors, report = _parse("vendors", xlsx(rows), "v.xlsx")
    assert vendors == [{"party_name": "ABC Pharma Distributors", "email": "accounts@abcpharma.example",
                        "is_email_valid": True}]
    assert (report["rows_read"], report["rows_kept"], report["rows_skipped"]) == (3, 1, 2)
    [typo], _ = _parse("vendors", xlsx([{"Vendor\nName": "Harkrishan Medicals",
                                         "Email ID": "harkrishan,medicals@gmail.com"}]), "v.xlsx")
    assert typo["is_email_valid"] is False and typo["email"] == "harkrishan,medicals@gmail.com"  # no guessing


def test_bank_keeps_debits_only():
    credit = {**fx.BANK_SOURCE[0], "Ref / Cheque No": "AXISCN1423459737", "Credit": "14,635.98", "Debit": "0.00"}
    rows, report = _parse("bank", xlsx([*fx.BANK_SOURCE, credit]), "b.xlsx")
    assert [r["utr"] for r in rows] == list(fx.BANK_TRANSACTIONS)
    assert rows[2]["debit"] == Decimal("525060.00") and rows[2]["vendor_name"] is None  # SAMPLE desc has no IFSC
    assert report["rows_skipped"] == 1


def test_fixture_consolidated_parses_to_expected_rows():
    rows, _ = _parse("consolidated", xlsx(fx.CONSOLIDATED_SOURCE), "c.xlsx")
    assert rows == fx.CONSOLIDATED_ENTRIES


def test_load_gdn_file_contract_function():
    [row] = load_gdn_file(io.BytesIO(xlsx(fx.GDN_SOURCE)))
    assert (row.invoice_no, row.amount, row.reason) == ("INV-2291", Decimal("20000.00"), "Goods returned (DN-0457)")
    with pytest.raises(ValueError, match="Narration"):
        load_gdn_file(io.BytesIO(xlsx([{"Particulars": "x", "Voucher Ref. No.": "y", "Gross Total": "1"}])))


def test_upload_stores_batch_and_summary(client, db):
    r = client.post("/api/batches", files=upload_files())
    assert r.status_code == 201, r.text
    assert "x-stub" not in r.headers
    batch_id = r.json()["id"]
    assert db.query(ConsolidatedEntry).filter_by(batch_id=batch_id).count() == 3
    assert db.query(Vendor).count() == 1

    s = client.get(f"/api/batches/{batch_id}/summary")
    assert s.status_code == 200 and "x-stub" not in s.headers
    assert s.json()["files"]["bank"]["rows_kept"] == 3
    assert client.get("/api/batches/999/summary").status_code == 404


def test_upload_rejects_bad_files_with_reasons(client, db):
    bad_bank = [{k: v for k, v in row.items() if k != "Debit"} for row in fx.BANK_SOURCE]
    r = client.post("/api/batches", files=upload_files(
        bank=("bank.xlsx", xlsx(bad_bank)),
        tds=("tds.csv", b"a,b"),
        gdn=("gdn.xlsx", b"\xd0\xcf\x11\xe0 protected"),
        vendors=("vendors.xlsx", b"PK\x03\x04 not really")))
    assert r.status_code == 422
    problems = {p["file"]: p["message"] for p in r.json()["detail"]}
    assert "not an Excel file" in problems["tds"]
    assert "password-protected" in problems["gdn"]
    assert set(problems) == {"tds", "gdn"}  # file checks run first; parsing waits until every file passes
    r = client.post("/api/batches", files=upload_files(bank=("bank.xlsx", xlsx(bad_bank))))
    assert r.json()["detail"] == [{"file": "bank", "message": 'missing column(s) "Debit"'}]
    r = client.post("/api/batches", files=upload_files(vendors=("vendors.xlsx", b"PK\x03\x04 not really")))
    assert "can't be read" in r.json()["detail"][0]["message"]
    assert db.query(ConsolidatedEntry).count() == 0  # nothing stored on failure
