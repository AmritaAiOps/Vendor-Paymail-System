"""Firebase login: every /api route except health depends on require_viewer (main.py); admin routes on require_admin.
Owner: Person A."""
from fastapi import Request

from app.schemas import MeOut


def require_viewer(request: Request) -> MeOut:  # STUB(contract)
    return MeOut(email="stub-admin@example.com", is_admin=True)


def require_admin(request: Request) -> MeOut:  # STUB(contract)
    return require_viewer(request)
