import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_setting, set_setting
from app.models import AuditLog, EmailHistory, EmailItem


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")  # the real migration, so triggers and constraints are under test
    engine = create_engine(url)
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_duplicate_utr_rejected(db):
    db.add(EmailItem(email_queue_id=1, reconciliation_result_id=1, utr="DLXBH00018402789"))
    db.commit()
    db.add(EmailItem(email_queue_id=2, reconciliation_result_id=2, utr="DLXBH00018402789"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_email_history_is_append_only(db):
    db.add(EmailHistory(vendor_name="KOMAL AGENCIES", status="SENT"))
    db.commit()
    for sql in ("UPDATE email_history SET status = 'FAILED'", "DELETE FROM email_history"):
        with pytest.raises(IntegrityError, match="append-only"):
            db.execute(text(sql))
        db.rollback()


def test_settings_roundtrip_and_audit(db):
    assert get_setting(db, "dry_run", "true") == "true"
    set_setting(db, "dry_run", "false", "admin")
    set_setting(db, "dry_run", "true", "admin")
    assert get_setting(db, "dry_run") == "true"
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    assert (last.old_value, last.new_value, last.who) == ("false", "true", "admin")
