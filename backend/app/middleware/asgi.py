"""Production entry point: uvicorn app.middleware.asgi:app.
shortcut: wraps app.main.app because main.py is shared and frozen; once main.py calls middleware.install(app)
(a contract change), point uvicorn back at app.main:app and delete this file."""
from app.main import app
from app.middleware import install

install(app)
