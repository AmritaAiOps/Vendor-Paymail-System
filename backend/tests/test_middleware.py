import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import JsonFormatter, install


def test_unhandled_error_is_json_500_without_traceback():
    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret detail")

    install(app)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger("app.errors").addHandler(handler)
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/boom", headers={"X-Request-ID": "abc123"})
    finally:
        logging.getLogger("app.errors").removeHandler(handler)
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error (ref abc123)"}  # contract error shape, no internals
    line = json.loads(JsonFormatter().format(records[0]))
    assert line["request_id"] == "abc123" and line["level"] == "ERROR" and "secret detail" in line["exc"]
