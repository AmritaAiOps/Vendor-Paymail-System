import os

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.auth import require_admin
from app.schemas import SettingsModel

router = APIRouter(prefix="/settings", tags=["settings"])

# Only the SettingsModel keys ever leave this router: config.get_setting refuses any other name, so no secret can.


def _current() -> SettingsModel:
    return SettingsModel(
        dry_run=config.get_setting("dry_run").strip().lower() not in ("false", "0", "no", "off"),  # same rule as sending.dry_run
        send_time=config.get_setting("send_time"), signature=config.get_setting("signature"))


def _as_stored(s: SettingsModel) -> dict[str, str]:
    return {"dry_run": "true" if s.dry_run else "false", "send_time": s.send_time, "signature": s.signature}


@router.get("", response_model=SettingsModel)
def get_settings():
    return _current()


@router.put("", response_model=SettingsModel, dependencies=[Depends(require_admin)])
def put_settings(body: SettingsModel):
    """send_time format and signature length are checked by SettingsModel (422). Only changed values are saved;
    config.set_setting writes one audit_log row per change. Admin only."""
    signature = body.signature.strip()
    if not signature:
        raise HTTPException(422, "Signature can't be empty")
    if any(c in signature for c in "\r\n\t"):
        raise HTTPException(422, "Signature must be one line")
    new = _as_stored(body.model_copy(update={"signature": signature}))
    old = _as_stored(_current())
    changed = {k: v for k, v in new.items() if v != old[k]}
    # Validate everything before writing anything: an env var wins on read, so saving it would silently do nothing
    if locked := [k.upper() for k in changed if os.environ.get(k.upper()) is not None]:
        raise HTTPException(409, f"Set in the server environment, change it there: {', '.join(locked)}")
    for k, v in changed.items():
        config.set_setting(k, v)
    return _current()
