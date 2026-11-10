import io
import zipfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from msoffcrypto.format.ooxml import OOXMLFile

from app.ingest import _parse, load_gdn_file
from app.ingest.clean import (cfa_company_key, clean_str, loose_name_key, name_key, normalize_utr, parse_amount,
                              parse_date, split_emails)
from app.models import ConsolidatedEntry, Vendor
from app.reconcile import _Vendors
from tests.fixtures import three_row_example as fx
from tests.util import files_from, post_batch, xlsx


def upload_files(**override) -> dict:
    return files_from(fx) | override


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
    assert loose_name_key("PHARMAGIX") == loose_name_key("Pharmagix(A Unit Of White Pharmaceuticals)")
    assert loose_name_key("AARK PHARMACEUTICALS PRIVATE LIMITED") == loose_name_key("Aark Pharmaceuticals")
    assert loose_name_key("M/S VALTURE PHARMACEUTICAL LLP") == loose_name_key("Valture Pharmaceutical")
    assert name_key("INTEGRA LIFE SCIENCES PRIVATE LIMITED") == name_key("Integra Life Sciences P Ltd") \
        == name_key("Integra Life Sciences (P) Ltd")
    assert name_key("UP Ltd") != name_key("U Pvt Ltd")  # only a standalone P
    assert cfa_company_key("Bansal Medical Hall (Macleods Cfa)") == loose_name_key("Macleods")
    for paid, listed in [("VARENYAM HEALTHCARE PRIVATE LIMITED", "Varenyam Healthcare - Cfa"),
                         ("WIN MEDICARE PRIVATE LIMITED", "Win Medicare Private Limited - Cfa Delhi"),
                         ("N.R.I. HEALTH AIDS", "Nri Health Aid"), ("DR. REDDYS LABORATORIES", "Dr. Reddy'S Laboratories"),
                         ("JB CHEMICAL & PHARMACEUTICALS LIMITED", "J.B Chemicals And Pharmaceuticals Ltd")]:
        assert loose_name_key(paid) == loose_name_key(listed), paid
    assert cfa_company_key("Anthus Pharmaceuticals (P) Ltd (Cfa)") is None and cfa_company_key("Roche (India)") is None


def test_vendor_lookup_company_vs_cfa():
    names = {"Aark Pharmaceuticals": "a@aark.in", "Aark Pharmaceuticals (Neon Cfa)": "neon@aark.in",
             "Bansal Medical Hall (Macleods Cfa)": "b@bansal.in", "Mankind Pharma Ltd. (Cfa -Delhi)": "r@mankind.com",
             "Mankind Pharma Ltd. (Cfa)": "R@mankind.com", "Zen Labs (North)": "n@zen.in", "Zen Labs (South)": "s@zen.in"}
    vendors = _Vendors([SimpleNamespace(party_name=n, email=e, pan=None) for n, e in names.items()])
    find = lambda n: getattr(vendors.find(n), "party_name", None)
    assert find("AARK PHARMACEUTICALS PRIVATE LIMITED") == "Aark Pharmaceuticals"  # not its CFA
    assert find("Macleods Pharmaceuticals Ltd") == "Bansal Medical Hall (Macleods Cfa)"  # through the CFA
    assert find("Bansal Medical Hall") == "Bansal Medical Hall (Macleods Cfa)"
    assert find("MANKIND PHARMA LIMITED DL") == "Mankind Pharma Ltd. (Cfa -Delhi)"  # both rows: same email
    assert find("ZEN LABS PVT LTD") is None  # two entries, two emails, neither is just the name: never guess
    assert find("Unknown Traders") is None


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
                        "is_email_valid": True, "pan": None}]
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
    r = post_batch(client, upload_files())
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
    r = post_batch(client, upload_files(
        bank=("bank.xlsx", xlsx(bad_bank)),
        tds=("tds.csv", b"a,b"),
        gdn=("gdn.xlsx", b"\xd0\xcf\x11\xe0 protected")))
    assert r.status_code == 422
    problems = {p["file"]: p["message"] for p in r.json()["detail"]}
    assert "not an Excel file" in problems["tds"]
    assert "not a valid .xlsx" in problems["gdn"]  # OLE2 signature, but not an encrypted workbook
    assert set(problems) == {"tds", "gdn"}  # file checks run first; parsing waits until every file passes
    r = post_batch(client, upload_files(bank=("bank.xlsx", xlsx(bad_bank))))
    assert r.json()["detail"] == [{"file": "bank", "message": 'missing column(s) "Debit"'}]
    assert db.query(ConsolidatedEntry).count() == 0  # nothing stored on failure


def test_upload_password_protected_files(client, db):
    locked = {}
    for kind in ("bank", "tds"):  # any file may be protected, each with its own password
        out = io.BytesIO()
        OOXMLFile(io.BytesIO(files_from(fx)[kind][1])).encrypt(f"{kind}-pw", out)
        locked[kind] = (f"{kind}.xlsx", out.getvalue())
    post = lambda **pw: post_batch(client, upload_files(**locked), data=pw)

    r = post(tds_password="tds-pw")
    assert r.status_code == 422 and r.json()["detail"] == [
        {"file": "bank", "message": "bank.xlsx is password-protected; enter its password", "password_required": True}]
    r = post(bank_password="nope", tds_password="tds-pw")
    assert "password is wrong" in r.json()["detail"][0]["message"] and r.json()["detail"][0]["password_required"]
    assert db.query(ConsolidatedEntry).count() == 0
    r = post(bank_password="bank-pw", tds_password="tds-pw")
    assert r.status_code == 201, r.text
    assert client.get(f"/api/batches/{r.json()['id']}/summary").json()["files"]["bank"]["rows_kept"] == 3


def test_upload_limits(client, db, monkeypatch):
    monkeypatch.setattr("app.config.MAX_UPLOAD_MB", 1)
    big = b"PK\x03\x04" + b"\0" * (1024 * 1024)
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sheet1.xml", b"\0" * (51 * 1024 * 1024))  # compresses to ~50 KB, unpacks past 50x 1 MB
    r = post_batch(client, upload_files(bank=("bank.xlsx", big), tds=("tds.xlsx", b""),
                                                       gdn=("gdn.xlsx", bomb.getvalue())))
    problems = {p["file"]: p["message"] for p in r.json()["detail"]}
    assert r.status_code == 422 and set(problems) == {"bank", "tds", "gdn"}
    assert "larger than 1 MB" in problems["bank"] and "is empty" in problems["tds"] and "unpacks to" in problems["gdn"]
    assert db.query(ConsolidatedEntry).count() == 0


def test_upload_file_name_is_cleaned(client, db):
    long_name = "C:\fakepath\\" + "x" * 300 + ".XLSX"
    r = post_batch(client, upload_files(vendors=(long_name, files_from(fx)["vendors"][1])))
    assert r.status_code == 201, r.text
    assert r.json()["vendors_file"] == "x" * 250 + ".xlsx"


def test_gdn_totals_rows_are_skipped():
    from app.ingest import _parse_gdn
    rep = {"rows_read": 0, "rows_rejected": 0, "issues": [], "rows_skipped": 0}
    raw = lambda v, inv: {"vendor_name": v, "invoice_no": inv, "voucher_no": "1", "gdn_date": None, "amount": "10", "reason": "r"}
    out = _parse_gdn([("APR", 2, raw("ACME", "A-1")), ("APR", 3, raw("Grand Total", None))], rep)
    assert [r["vendor_name"] for r in out] == ["ACME"] and rep["rows_skipped"] == 1
