from fastapi import APIRouter

from app.routers import STUB
from app.schemas import SettingsModel

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsModel, dependencies=[STUB])
def get_settings():
    return SettingsModel(dry_run=True, send_time="10:00")


@router.put("", response_model=SettingsModel, dependencies=[STUB])
def put_settings(body: SettingsModel):
    return body
