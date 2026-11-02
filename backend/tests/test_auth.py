"""Firebase login checks, no network: firebase_admin.auth.verify_id_token is mocked."""
import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth as fb

from app import config
from app.main import app
from app.models import get_db

ADMIN, VIEWER = "boss@other.com", "clerk@pharma.test"
ADMIN_ROUTES = [("POST", "/api/scheduler/run-now"), ("POST", "/api/email-history/rebuild-xlsx"),
                ("PUT", "/api/settings")]


@pytest.fixture
def api(db, monkeypatch):
    """Real auth dependencies; the token string is the email it 'verifies' as, or the name of an error to raise."""
    monkeypatch.setattr(config, "FIREBASE_PROJECT_ID", "paymail-test")
    monkeypatch.setattr(config, "ALLOWED_EMAIL_DOMAIN", "pharma.test")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {ADMIN})

    def verify(token, app=None, check_revoked=False, clock_skew_seconds=0):
        assert clock_skew_seconds == 10
        if token == "expired":
            raise fb.ExpiredIdTokenError("expired", None)
        if token in ("garbage", "wrong-project"):
            raise fb.InvalidIdTokenError(token)
        email, _, flag = token.partition("|")
        return {"email": email, "email_verified": flag != "unverified"}

    monkeypatch.setattr(fb, "verify_id_token", verify)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _get(api, token=None, path="/api/auth/me"):
    return api.get(path, headers={"Authorization": f"Bearer {token}"} if token else {})


@pytest.mark.parametrize("token", [None, "garbage", "expired", "wrong-project"])
def test_bad_token_is_401(api, token):
    r = _get(api, token)
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"


def test_non_bearer_scheme_is_401(api):
    assert api.get("/api/auth/me", headers={"Authorization": f"Basic {VIEWER}"}).status_code == 401


@pytest.mark.parametrize("token", [f"{VIEWER}|unverified", "someone@elsewhere.com", "x@notpharma.test"])
def test_not_allowed_is_403(api, token):
    assert _get(api, token).status_code == 403


def test_me(api):
    assert _get(api, VIEWER).json() == {"email": VIEWER, "is_admin": False}
    assert _get(api, ADMIN.upper()).json() == {"email": ADMIN, "is_admin": True}  # admin outside the domain is fine


def test_protected_route_needs_token(api):
    assert _get(api, None, "/api/settings").status_code == 401
    assert _get(api, VIEWER, "/api/settings").status_code == 200


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes(api, method, path):
    body = {"json": {"dry_run": True, "send_time": "10:00", "signature": "S"}} if method == "PUT" else {}
    as_viewer = api.request(method, path, headers={"Authorization": f"Bearer {VIEWER}"}, **body)
    assert as_viewer.status_code == 403
    as_admin = api.request(method, path, headers={"Authorization": f"Bearer {ADMIN}"}, **body)
    assert as_admin.status_code not in (401, 403)


def test_health_is_open(api):
    assert _get(api, None, "/api/health").status_code == 200


def test_no_project_fails_closed(api, monkeypatch):
    monkeypatch.setattr(config, "FIREBASE_PROJECT_ID", "")
    assert _get(api, ADMIN).status_code == 503
    assert _get(api, None, "/api/health").status_code == 200
