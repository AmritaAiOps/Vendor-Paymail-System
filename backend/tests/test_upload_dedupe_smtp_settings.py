"""Duplicate uploads, superseded exceptions/manual review rows, the SMTP settings API and IST timestamps."""
from datetime import timedelta

import pytest

from app import config
from app.models import AuditLog, UploadBatch
from tests.fixtures import special_cases as sc
from tests.test_sending import smtp  # noqa: F401  (fixture)
from tests.util import files_from, xlsx

SECRET = "hunter2-SMTP-SECRET"


@pytest.fixture(autouse=True)
def no_smtp_env(monkeypatch):
    for k in config.SMTP_SETTINGS:
        monkeypatch.delenv(k.upper(), raising=False)


def upload(client, files):
    return client.post("/api/batches", files=files)


def test_same_five_files_twice_is_refused_and_names_the_batch(client, db):
    first = upload(client, files_from(sc))
    assert first.status_code == 201
    again = upload(client, files_from(sc))
    assert again.status_code == 409 and f"batch {first.json()['id']}" in again.json()["detail"]
    assert db.query(UploadBatch).count() == 1


def test_uploaded_at_is_ist(client, db):
    upload(client, files_from(sc))
    assert abs(db.query(UploadBatch).one().uploaded_at - config.now_ist()) < timedelta(minutes=1)


def test_a_newer_batch_replaces_the_same_invoices_on_exceptions_and_manual_review(client):
    files = files_from(sc)
    one = upload(client, files).json()["id"]
    client.post(f"/api/batches/{one}/reconcile")
    exceptions, review = client.get("/api/exceptions").json(), client.get("/api/manual-review").json()
    assert exceptions or review  # the fixture has some of each

    # Same invoices, a vendor list with one extra row: different bytes, so not a duplicate upload
    files["vendors"] = ("vendors.xlsx", xlsx(sc.VENDORS_SOURCE + [{"Vendor\nName": "Extra Co", "Email ID": "a@extra.example"}]))
    two = upload(client, files).json()["id"]
    assert len(client.get("/api/exceptions").json()) == len(exceptions)  # newer batch not reconciled yet: old rows stay
    client.post(f"/api/batches/{two}/reconcile")
    for path, before in (("/api/exceptions", exceptions), ("/api/manual-review", review)):
        rows = client.get(path).json()
        assert len(rows) == len(before) and {r["batch_id"] for r in rows} <= {two}


def test_smtp_settings_save_never_return_the_password(client, db):
    assert client.get("/api/settings/smtp").json() == {
        "host": "", "port": 587, "user": "", "password_set": False, "from_email": "",
        "from_name": "Sudhamayi Enterprises Pvt. Ltd.", "starttls": True, "locked": []}
    body = {"host": "smtp.example.com", "port": 465, "user": "mailer", "password": SECRET,
            "from_email": "payments@example.com", "from_name": "Payments", "starttls": False}
    r = client.put("/api/settings/smtp", json=body)
    assert r.status_code == 200 and SECRET not in r.text and r.json()["password_set"] is True
    assert config.smtp()["password"] == SECRET and config.smtp()["port"] == 465
    assert all(SECRET not in (a.old_value or "") + (a.new_value or "") for a in db.query(AuditLog))

    # Blank password keeps the saved one
    client.put("/api/settings/smtp", json={**body, "password": "", "host": "smtp2.example.com"})
    assert config.smtp()["password"] == SECRET and config.smtp()["host"] == "smtp2.example.com"


def test_smtp_settings_reject_env_locked_and_bad_from(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "env.example.com")
    body = {"host": "ui.example.com", "port": 587, "user": "", "password": None,
            "from_email": "payments@example.com", "from_name": "Payments", "starttls": True}
    r = client.put("/api/settings/smtp", json=body)
    assert r.status_code == 409 and "SMTP_HOST" in r.json()["detail"]
    assert client.get("/api/settings/smtp").json()["locked"] == ["host"]
    assert client.put("/api/settings/smtp", json={**body, "host": "env.example.com", "from_email": "nope"}).status_code == 422


def test_smtp_test_email_goes_to_the_signed_in_admin(client, smtp, monkeypatch):
    r = client.post("/api/settings/smtp/test")
    assert r.status_code == 200 and r.json() == {"sent_to": "admin@example.com"}
    assert [m["To"] for m in smtp.sent] == ["admin@example.com"]
    monkeypatch.delenv("SMTP_HOST")
    assert client.post("/api/settings/smtp/test").status_code == 422


def test_email_sample_uses_the_saved_signature(client):
    client.put("/api/settings", json={"dry_run": True, "send_time": "10:00", "signature": "Asha, Accounts"})
    r = client.get("/api/settings/email-sample").json()
    assert "Sample Vendor" in r["subject"] and "Asha, Accounts" in r["html"] and "INV-1003" in r["html"]
