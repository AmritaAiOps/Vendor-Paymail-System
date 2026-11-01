import io
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, ingest, reconcile
from app.contract import ResultStatus
from app.history.audit import log_change
from app.models import ConsolidatedEntry, ReconciliationResult, get_db
from app.reports.results import results_out
from app.schemas import GdnUploadOut, ReasonIn, ResultOut

router = APIRouter(prefix="/manual-review", tags=["manual-review"])
_waiting = ReconciliationResult.status == ResultStatus.MANUAL_REVIEW


@router.get("", response_model=list[ResultOut])
def manual_review(db: Session = Depends(get_db)):
    return results_out(db, _waiting)


@router.put("/{result_id}/reason", response_model=ResultOut)
def set_reason(result_id: int, body: ReasonIn, request: Request, db: Session = Depends(get_db)):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(422, "The reason can't be blank")
    result = db.get(ReconciliationResult, result_id)
    if result is None:
        raise HTTPException(404, "Result not found")
    if result.status != ResultStatus.MANUAL_REVIEW:
        raise HTTPException(409, "This item is not waiting for manual review")
    old = result.reason
    try:
        reconcile.requeue_after_reason(db, result_id, reason)  # sets the reason, moves it to DEDUCTION, queues the email
    except ValueError as err:  # e.g. nothing a reason could explain (overpaid)
        raise HTTPException(422, str(err))
    log_change(db, request, f"manual review: reason set on reconciliation_result {result_id}", old, reason)
    db.commit()
    return results_out(db, ReconciliationResult.id == result_id)[0]


def _simple(name: str) -> str:
    # shortcut: letters and digits only; ingest's name_key (Pvt/Ltd folding) is not part of the contract, so it is not used here
    return re.sub(r"[^a-z0-9]", "", name.lower())


@router.post("/gdn-upload", response_model=GdnUploadOut)
def gdn_upload(file: UploadFile, request: Request, db: Session = Depends(get_db)):
    """Read an updated GDN Report and use its narration as the reason for matching manual-review items."""
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(422, "Only .xlsx or .xls files are accepted")
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(422, f"File is over {config.MAX_UPLOAD_MB} MB")
    try:
        rows = ingest.load_gdn_file(io.BytesIO(data))
    except ValueError as err:
        raise HTTPException(422, str(err))

    waiting = defaultdict(list)  # invoice no -> [(result id, vendor name)]
    for rid, vendor, invoice in db.execute(
            select(ReconciliationResult.id, ConsolidatedEntry.vendor_name, ConsolidatedEntry.invoice_no)
            .join(ConsolidatedEntry, ConsolidatedEntry.id == ReconciliationResult.consolidated_entry_id).where(_waiting)):
        waiting[invoice.strip().casefold()].append((rid, vendor))
    reasons = defaultdict(list)  # result id -> narrations
    for g in rows:
        reason = (g.reason or "").strip()
        if not (g.invoice_no and reason):
            continue
        found = waiting.get(g.invoice_no.strip().casefold(), [])
        if len(found) > 1:  # the same invoice no under several vendors: keep the one whose name matches
            found = [f for f in found if _simple(f[1]) == _simple(g.vendor_name)]
        if len(found) == 1 and reason not in reasons[found[0][0]]:
            reasons[found[0][0]].append(reason)

    requeued = 0
    for rid, texts in reasons.items():
        try:
            reconcile.requeue_after_reason(db, rid, "; ".join(texts))
            requeued += 1
        except ValueError:  # no deduction to explain, or the joined text is over 500 characters: leave it in review
            db.rollback()
    log_change(db, request, f"manual review: GDN file {file.filename!r} read, {len(rows)} rows, {requeued} items queued", None, None)
    db.commit()
    return GdnUploadOut(rows_read=len(rows), requeued=requeued)
