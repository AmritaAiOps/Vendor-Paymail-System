import pytest

from app import config
from app.models import AppSetting, AuditLog

SECRET = "hunter2-SMTP-SECRET"
GOOD = {"dry_run": True, "send_time": "10:00", "signature": "Ravi Kumar, Accounts"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("DRY_RUN", "SEND_TIME", "SIGNATURE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SMTP_PASSWORD", SECRET)
    monkeypatch.setattr(config, "SMTP_PASSWORD", SECRET)
    monkeypatch.setattr(config, "SMTP_USER", SECRET)


def test_defaults_and_save_audits_each_change(client, db):
    r = client.get("/api/settings")
    assert r.status_code == 200 and "x-stub" not in r.headers
    assert r.json() == {"dry_run": True, "send_time": "10:00", "signature": "[Name, designation]"}

    r = client.put("/api/settings", json={**GOOD, "dry_run": False, "signature": "  Ravi Kumar, Accounts  "})
    assert r.json() == {"dry_run": False, "send_time": "10:00", "signature": "Ravi Kumar, Accounts"}
    assert client.get("/api/settings").json() == r.json()
    audits = db.query(AuditLog).order_by(AuditLog.id).all()
    assert [(a.what, a.new_value) for a in audits] == [("setting:dry_run", "false"), ("setting:signature", "Ravi Kumar, Accounts")]

    client.put("/api/settings", json=r.json())  # unchanged: nothing written
    assert db.query(AuditLog).count() == 2


@pytest.mark.parametrize("bad", [
    {"send_time": "25:00"}, {"send_time": "9:00"}, {"send_time": "10:00:00"}, {"send_time": ""},
    {"signature": "   "}, {"signature": "x" * 501}, {"signature": "two\nlines"},
    {"dry_run": "maybe"}, {"dry_run": None},
])
def test_invalid_values_rejected_and_nothing_saved(client, db, bad):
    r = client.put("/api/settings", json={**GOOD, "dry_run": False, **bad})
    assert r.status_code == 422
    assert db.query(AppSetting).count() == 0 and db.query(AuditLog).count() == 0


def test_env_override_is_refused_not_silently_ignored(client, db, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    r = client.put("/api/settings", json={**GOOD, "dry_run": False, "send_time": "09:30"})
    assert r.status_code == 409 and "DRY_RUN" in r.json()["detail"]
    assert db.query(AppSetting).count() == 0  # send_time wasn't saved either
    assert client.put("/api/settings", json={**GOOD, "send_time": "09:30"}).json()["send_time"] == "09:30"


def test_no_secret_in_any_settings_response(client):
    for r in (client.get("/api/settings"), client.put("/api/settings", json=GOOD),
              client.put("/api/settings", json={**GOOD, "send_time": "bad"})):
        assert SECRET not in r.text
        if r.status_code == 200:
            assert set(r.json()) == {"dry_run", "send_time", "signature"}
