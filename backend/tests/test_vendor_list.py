"""The stored vendors list (first-time block, preview/replace, edit table, versions, concurrency), the matching engine
reading it, and the pending-mail summary behind the exit pop-up and the missing-UTR notification."""
from datetime import datetime

import pytest

from app import config, vendor_list
from app.models import ConsolidatedEntry, EmailQueue, Vendor, VendorListHistory
from tests.fixtures import special_cases as sc
from tests.fixtures import three_row_example as fx
from tests.test_sending import smtp  # noqa: F401  (fixture)
from tests.util import files_from, post_batch, seed_list, xlsx

LIST = [{"Vendor\nName": "Alpha Pharma", "Email ID": "a@alpha.example"},
        {"Vendor\nName": "Beta Medicos", "Email ID": "b@beta.example"},
        {"Vendor\nName": "Gamma Labs", "Email ID": "g@gamma.example"}]


def file(rows=LIST, name="vendors.xlsx"):
    return {"file": (name, xlsx(rows))}


def replace(client, rows=LIST, base=0, name="vendors.xlsx"):
    return client.post("/api/vendor-list/replace", files=file(rows, name), data={"base_version": base})


def status(client):
    return client.get("/api/vendor-list").json()


def table(client):
    return client.get("/api/vendor-list/vendors").json()


def save(client, rows, base):
    return client.put("/api/vendor-list/vendors", json={"base_version": base, "vendors": rows})


# --- first-time setup ------------------------------------------------------------------------------------------------

def test_no_list_yet_blocks_the_run(client, db):
    assert status(client) == {"exists": False, "version": 0, "file_name": None, "updated_at": None, "updated_by": None, "total": 0}
    files = files_from(fx)
    r = client.post("/api/batches", files={k: v for k, v in files.items() if k != "vendors"})
    assert r.status_code == 409 and "No vendors list" in r.json()["detail"]
    assert db.query(ConsolidatedEntry).count() == 0


def test_reconcile_is_blocked_without_a_list(client, db):
    seed_list(client, files_from(fx))
    batch_id = client.post("/api/batches", files={k: v for k, v in files_from(fx).items() if k != "vendors"}).json()["id"]
    db.query(Vendor).delete()
    db.execute(vendor_list.VendorListState.__table__.delete())
    db.commit()
    assert client.post(f"/api/batches/{batch_id}/reconcile").status_code == 409


def test_first_upload_stores_the_list_for_everyone(client, db):
    r = replace(client, name="Vendor Contact List.xlsx")
    assert r.status_code == 200, r.text
    s = r.json()["status"]
    assert (s["exists"], s["version"], s["total"], s["file_name"], s["updated_by"]) == (
        True, 1, 3, "Vendor Contact List.xlsx", "admin@example.com")
    assert abs(datetime.fromisoformat(s["updated_at"]) - config.now_ist()).total_seconds() < 60
    assert [v["party_name"] for v in table(client)["vendors"]] == ["Alpha Pharma", "Beta Medicos", "Gamma Labs"]


# --- re-upload: preview, diff, confirm -------------------------------------------------------------------------------

def test_preview_shows_new_removed_changed_and_stores_nothing(client, db):
    replace(client)
    newer = [{"Vendor\nName": "alpha pharma", "Email ID": "a@alpha.example"},      # same vendor, same email
             {"Vendor\nName": "Beta Medicos", "Email ID": "new@beta.example"},     # changed email
             {"Vendor\nName": "Delta Care", "Email ID": "d@delta.example"}]        # new; Gamma Labs is gone
    r = client.post("/api/vendor-list/preview", files=file(newer, "v2.xlsx"))
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["file_name"], p["total"], p["base_version"], p["unchanged"]) == ("v2.xlsx", 3, 1, 0)
    assert [v["party_name"] for v in p["new"]] == ["Delta Care"]
    assert [v["party_name"] for v in p["removed"]] == ["Gamma Labs"]
    assert {c["old_party_name"]: c["new_email"] for c in p["changed"]} == {"Alpha Pharma": "a@alpha.example", "Beta Medicos": "new@beta.example"}
    assert status(client)["version"] == 1 and len(table(client)["vendors"]) == 3  # a preview changes nothing


def test_replace_applies_the_diff_and_keeps_removed_vendors_as_inactive_rows(client, db):
    replace(client)
    gamma_id = next(v["id"] for v in table(client)["vendors"] if v["party_name"] == "Gamma Labs")
    r = replace(client, [LIST[0], {"Vendor\nName": "Delta Care", "Email ID": "d@delta.example"}], base=1, name="v2.xlsx")
    assert r.status_code == 200 and r.json()["status"]["version"] == 2 and r.json()["status"]["total"] == 2
    assert [v["party_name"] for v in table(client)["vendors"]] == ["Alpha Pharma", "Delta Care"]
    assert db.get(Vendor, gamma_id).is_active is False  # still there for old results and emails
    back = replace(client, LIST, base=2)  # Gamma Labs returns as the same vendor, not a duplicate row
    assert back.status_code == 200
    assert db.get(Vendor, gamma_id).is_active is True and db.query(Vendor).count() == 4


def test_identical_file_changes_nothing(client, db):
    replace(client)
    r = replace(client, base=1, name="same-again.xlsx")
    assert r.status_code == 200 and r.json()["status"]["version"] == 1
    assert db.query(VendorListHistory).count() == 1


@pytest.mark.parametrize("data, message", [
    (b"PK\x03\x04 not really", "can't be read"),
    (xlsx([{"Name": "x", "Mail": "y"}]), "missing column"),
    (b"just text", "not a valid"),
])
def test_bad_file_gives_a_clear_error_and_keeps_the_old_list(client, db, data, message):
    replace(client)
    for path, extra in (("preview", {}), ("replace", {"base_version": 1})):
        r = client.post(f"/api/vendor-list/{path}", files={"file": ("vendors.xlsx", data)}, data=extra)
        assert r.status_code == 422 and message in r.json()["detail"][0]["message"], r.text
    assert status(client)["version"] == 1 and len(table(client)["vendors"]) == 3


def test_not_an_excel_file_is_refused(client):
    r = client.post("/api/vendor-list/preview", files={"file": ("vendors.csv", b"a,b")})
    assert r.status_code == 422 and "not an Excel file" in r.json()["detail"][0]["message"]


# --- edit table ------------------------------------------------------------------------------------------------------

def test_edit_adds_changes_and_deletes_vendors(client, db):
    replace(client)
    rows = table(client)["vendors"]
    alpha, beta, gamma = rows
    r = save(client, [
        {**alpha, "email": "new@alpha.example; second@alpha.example"},   # edited (two addresses)
        beta,                                                              # untouched
        {"id": None, "party_name": "  Delta   Care ", "email": "d@delta.example"},  # added
    ], base=1)                                                             # Gamma deleted
    assert r.status_code == 200, r.text
    assert r.json()["status"]["version"] == 2 and r.json()["status"]["total"] == 3
    now = {v["party_name"]: v["email"] for v in table(client)["vendors"]}
    assert now == {"Alpha Pharma": "new@alpha.example, second@alpha.example", "Beta Medicos": "b@beta.example",
                   "Delta Care": "d@delta.example"}
    assert db.get(Vendor, gamma["id"]).is_active is False
    last = db.query(VendorListHistory).order_by(VendorListHistory.id.desc()).first()
    assert (last.action, last.user, last.added, last.removed, last.changed) == ("EDIT", "admin@example.com", 1, 1, 1)


def test_edit_validates_every_row_and_saves_nothing(client, db):
    replace(client)
    ok = table(client)["vendors"]
    bad = save(client, [
        {"id": None, "party_name": "   ", "email": "x@y.example"},
        {"id": None, "party_name": "Fresh Co", "email": "not-an-email"},
        {"id": None, "party_name": "Fresh Co", "email": ""},
        {**ok[0], "party_name": "BETA MEDICOS"},   # same name as row 2 once case and punctuation are ignored
        ok[1],
    ], base=1)
    assert bad.status_code == 422
    by_row = {(p["row"], p["field"]): p["message"] for p in bad.json()["detail"]}
    assert "can't be empty" in by_row[(0, "party_name")]
    assert "valid email" in by_row[(1, "email")]
    assert "listed twice" in by_row[(2, "party_name")] and "Email id is empty" in by_row[(2, "email")]
    assert "listed twice (also row 4)" in by_row[(4, "party_name")]  # "BETA MEDICOS" and "Beta Medicos"
    assert status(client)["version"] == 1 and [v["party_name"] for v in table(client)["vendors"]] == [v["party_name"] for v in ok]
    assert save(client, [], base=1).status_code == 422  # an empty list is never saved


def test_unchanged_edit_makes_no_new_version(client):
    replace(client)
    r = save(client, table(client)["vendors"], base=1)
    assert r.status_code == 200 and r.json()["status"]["version"] == 1


def test_a_removed_name_can_be_taken_by_another_vendor(client, db):
    replace(client)
    alpha, beta, gamma = table(client)["vendors"]
    r = save(client, [alpha, {**beta, "party_name": "Gamma Labs"}], base=1)  # Gamma deleted, Beta renamed to Gamma
    assert r.status_code == 200, r.text
    assert [v["party_name"] for v in table(client)["vendors"]] == ["Alpha Pharma", "Gamma Labs"]


# --- two users at once -----------------------------------------------------------------------------------------------

def test_a_stale_save_is_refused_and_does_not_overwrite(client, db):
    replace(client)
    mine = table(client)  # both users load version 1
    theirs = table(client)
    first = save(client, [{**theirs["vendors"][0], "email": "theirs@alpha.example"}, *theirs["vendors"][1:]], base=theirs["version"])
    assert first.status_code == 200
    second = save(client, [{**mine["vendors"][0], "email": "mine@alpha.example"}, *mine["vendors"][1:]], base=mine["version"])
    assert second.status_code == 409 and "changed by admin@example.com" in second.json()["detail"]
    assert next(v["email"] for v in table(client)["vendors"] if v["party_name"] == "Alpha Pharma") == "theirs@alpha.example"
    stale_upload = replace(client, LIST[:1], base=1)  # a re-upload based on version 1 is just as stale
    assert stale_upload.status_code == 409 and status(client)["total"] == 3


def test_two_first_uploads_cannot_both_win(client):
    assert replace(client).status_code == 200
    assert replace(client, LIST[:1], base=0).status_code == 409


# --- history ---------------------------------------------------------------------------------------------------------

def test_history_records_every_change(client):
    replace(client, name="first.xlsx")
    save(client, table(client)["vendors"][:2], base=1)
    alpha = table(client)["vendors"][0]
    client.put(f"/api/vendors/{alpha['id']}/email", json={"email": "fixed@alpha.example"})
    h = client.get("/api/vendor-list/history").json()
    assert [(x["version"], x["action"], x["user"]) for x in h] == [
        (3, "EMAIL_FIX", "admin@example.com"), (2, "EDIT", "admin@example.com"), (1, "UPLOAD", "admin@example.com")]
    assert h[2]["file_name"] == "first.xlsx" and h[2]["vendor_count"] == 3 and h[1]["removed"] == 1
    assert status(client)["version"] == 3


# --- the engine reads the stored list --------------------------------------------------------------------------------

def test_matching_uses_the_stored_list_not_the_uploaded_files(client, db):
    assert post_batch(client, files_from(fx)).status_code == 201  # the batch upload carries no vendors file
    batch_id = db.query(ConsolidatedEntry.batch_id).first()[0]
    # the three-row example's vendor is not on the stored list: every invoice is VENDOR_NOT_FOUND, even though the
    # list the example came with does have it
    assert replace(client, LIST, base=status(client)["version"]).status_code == 200
    client.post(f"/api/batches/{batch_id}/reconcile")
    rows = client.get(f"/api/batches/{batch_id}/results").json()
    assert len(rows) == 3 and {r["exception_type"] for r in rows} == {"VENDOR_NOT_FOUND"}

    # add the vendor through the edit table; the next run matches it
    (name,) = {r["vendor_name"] for r in rows}
    v = table(client)
    save(client, [*v["vendors"], {"id": None, "party_name": name, "email": "accounts@vendor.example"}], base=v["version"])
    client.post(f"/api/batches/{batch_id}/reconcile")
    after = client.get(f"/api/batches/{batch_id}/results").json()
    assert {r["exception_type"] for r in after} != {"VENDOR_NOT_FOUND"} and all(r["vendor_id"] for r in after)


# --- pending mails + missing UTRs (exit pop-up, notification) --------------------------------------------------------

def reconciled_special_cases(client):
    batch = post_batch(client, files_from(sc)).json()["id"]
    client.post(f"/api/batches/{batch}/reconcile")


def test_pending_summary_lists_scheduled_mails_with_time_and_missing_utrs(client, db):
    assert client.get("/api/email-queue/pending-summary").json() == {"total": 0, "missing_utr_mails": 0, "missing_utr_invoices": 0, "items": []}
    reconciled_special_cases(client)
    s = client.get("/api/email-queue/pending-summary").json()
    assert s["total"] == len(s["items"]) == db.query(EmailQueue).filter(EmailQueue.status == "PENDING").count() > 0
    first = s["items"][0]
    assert set(first) == {"id", "vendor_id", "vendor_name", "invoice_count", "send_on_date", "scheduled_at", "missing_utr_count"}
    assert first["scheduled_at"].startswith(f"{first['send_on_date']}T10:00:00") and first["scheduled_at"].endswith("+05:30")
    sunrise = [i for i in s["items"] if i["vendor_name"] == "Sunrise Pharma"]
    assert sunrise and all(i["missing_utr_count"] == 1 for i in sunrise)  # INV-S12 has a blank UTR
    assert s["missing_utr_mails"] == len(sunrise) and s["missing_utr_invoices"] >= 1
    assert all(i["missing_utr_count"] == 0 for i in s["items"] if i["vendor_name"] != "Sunrise Pharma")


def test_send_all_now_holds_flagged_mails_unless_told_otherwise(client, db, smtp, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DRY_RUN", "false")
    reconciled_special_cases(client)
    items = client.get("/api/email-queue/pending-summary").json()["items"]
    flagged = [i["id"] for i in items if i["missing_utr_count"]]
    ids = [i["id"] for i in items]
    assert flagged and len(flagged) < len(ids)

    r = client.post("/api/email-queue/send-all-now", json={"ids": ids})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["held"] == len(flagged) and out["sent"] == len(ids) - len(flagged) and out["failed"] == 0
    left = client.get("/api/email-queue/pending-summary").json()
    assert {i["id"] for i in left["items"]} == set(flagged)  # held mails stay scheduled

    again = client.post("/api/email-queue/send-all-now", json={"ids": ids}).json()
    assert again["held"] == len(flagged) and again["already_done"] == len(ids) - len(flagged)

    forced = client.post("/api/email-queue/send-all-now", json={"ids": flagged, "include_missing_utr": True}).json()
    assert forced["sent"] == len(flagged) and forced["held"] == 0
    assert client.get("/api/email-queue/pending-summary").json()["total"] == 0


def test_send_all_now_needs_ids(client):
    assert client.post("/api/email-queue/send-all-now", json={"ids": []}).status_code == 422
