"""The stored vendors list (see app.vendor_list): status card, edit table, re-upload with a preview, version history.
Any signed-in user may view and change it; the history records who."""
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import vendor_list
from app.auth import require_viewer
from app.ingest import FileError, parse_vendors_file
from app.models import get_db
from app.routers.batches import _check_upload
from app.schemas import (MeOut, RowIssue, VendorHistoryOut, VendorListIn, VendorListOut, VendorListStatus,
                         VendorPreviewOut, VendorRow, VendorSaveOut)

router = APIRouter(prefix="/vendor-list", tags=["vendor-list"])


def _conflict(e: vendor_list.Conflict) -> HTTPException:
    return HTTPException(409, str(e))


def _parsed(file: UploadFile, password: str | None) -> tuple[str, list[dict], dict]:
    """(file name, rows, report) of an uploaded vendors list. 422 [{file, message}] if it can't be used; the stored list
    is never touched by this."""
    checked = _check_upload("vendors", file, password)
    if isinstance(checked, dict):
        raise HTTPException(422, [checked])
    name, data = checked
    try:
        rows, report = parse_vendors_file(data, name)
    except FileError as e:
        raise HTTPException(422, e.problems)
    return name, rows, report


@router.get("", response_model=VendorListStatus)
def get_status(db: Session = Depends(get_db)):
    return vendor_list.status(db)


@router.get("/vendors", response_model=VendorListOut)
def get_vendors(db: Session = Depends(get_db)):
    """The list for the edit table, with the version to send back when saving."""
    return VendorListOut(version=vendor_list.status(db)["version"],
                         vendors=[VendorRow(id=v.id, party_name=v.party_name, email=v.email) for v in vendor_list.active(db)])


@router.put("/vendors", response_model=VendorSaveOut)
def save_vendors(body: VendorListIn, me: MeOut = Depends(require_viewer), db: Session = Depends(get_db)):
    """Save the edit table. 422 detail = [{row, field, message}] for every problem (nothing saved); 409 if somebody saved
    the list since base_version (nothing saved)."""
    try:
        return vendor_list.edit(db, [r.model_dump() for r in body.vendors], me.email, body.base_version)
    except vendor_list.Invalid as e:
        raise HTTPException(422, e.problems)
    except vendor_list.Conflict as e:
        raise _conflict(e)


@router.post("/preview", response_model=VendorPreviewOut)
def preview(file: UploadFile, password: str | None = Form(None, max_length=255), db: Session = Depends(get_db)):
    """Read a vendors list file and say what replacing the stored list with it would change. Nothing is stored.
    422 detail = [{file, message}] if the file is corrupt or has the wrong columns (password_required: true if protected)."""
    name, rows, report = _parsed(file, password)
    changes = vendor_list.diff(db, rows)
    return VendorPreviewOut(file_name=name, total=len(rows), base_version=vendor_list.status(db)["version"],
                            new=changes["new"], removed=changes["removed"], changed=changes["changed"],
                            unchanged=changes["unchanged"], issues=[RowIssue(**i) for i in report["issues"]])


@router.post("/replace", response_model=VendorSaveOut)
def replace(file: UploadFile, base_version: int = Form(ge=0), password: str | None = Form(None, max_length=255),
            me: MeOut = Depends(require_viewer), db: Session = Depends(get_db)):
    """Replace the stored list with the file (the confirmed preview). base_version 0 = first-time setup. The file is read
    and checked first: any problem is a 422 and the old list stays. 409 if somebody saved since base_version."""
    name, rows, _ = _parsed(file, password)
    try:
        return vendor_list.replace(db, rows, name, me.email, base_version)
    except vendor_list.Conflict as e:
        raise _conflict(e)


@router.get("/history", response_model=list[VendorHistoryOut])
def history(limit: int = 100, db: Session = Depends(get_db)):
    """Every change to the list, newest first: when, who, what."""
    return [VendorHistoryOut.model_validate(h, from_attributes=True) for h in vendor_list.history(db, min(max(limit, 1), 500))]
