from fastapi import APIRouter

from app.routers import stub

router = APIRouter(prefix="/settings", tags=["settings"])

EXAMPLE = {"dry_run": "true", "send_time": "10:00"}  # keys/values as stored in app_settings


@router.get("")
def get_settings():
    return stub(EXAMPLE)


@router.put("")
def put_settings(body: dict[str, str]):
    return stub(EXAMPLE)
