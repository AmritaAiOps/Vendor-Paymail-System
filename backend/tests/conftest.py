import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import require_admin, require_viewer
from app.main import app
from app.models import get_db
from app.schemas import MeOut


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")  # the real migration, so triggers and constraints are under test
    engine = create_engine(url)
    monkeypatch.setattr("app.models.SessionLocal", sessionmaker(engine))  # config.get/set_setting open their own
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture
def client(db):
    """API client whose requests use the test database."""
    app.dependency_overrides[get_db] = lambda: db
    signed_in = lambda: MeOut(email="admin@example.com", is_admin=True)  # tests/test_auth.py tests the real checks
    app.dependency_overrides[require_viewer] = signed_in
    app.dependency_overrides[require_admin] = signed_in
    yield TestClient(app)
    app.dependency_overrides.clear()
