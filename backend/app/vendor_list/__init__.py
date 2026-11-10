"""The stored vendors list: uploaded or edited once, used by every run and every user.

The list lives in the `vendors` table (the matching engine, email builder and sender already read it from there);
`vendor_list_state` says who last changed it and at which version, and `vendor_list_history` logs every change.
A vendor removed from the list is switched off (is_active = False), not deleted, so old results keep their vendor.

Concurrency: every change names the version it was based on (`base_version`) and bumps it with one conditional UPDATE.
If somebody saved in between, nothing is written and Conflict says who and when, so no one overwrites silently.
Nothing is written until the whole new list has been read and checked, so a bad file leaves the old list intact."""
import logging
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.ingest.clean import name_key, split_emails
from app.models import Vendor, VendorListHistory, VendorListState

log = logging.getLogger(__name__)
_DETAIL_CAP = 200  # names kept per list in a history entry's details


class Conflict(Exception):
    """The list changed since the caller loaded it. state = the newer version (None if it was only just created)."""

    def __init__(self, state: VendorListState | None):
        self.state = state
        who = f"{state.updated_by} at {state.updated_at:%d %b %Y, %H:%M}" if state else "another user"
        super().__init__(f"The vendors list was changed by {who} while you were working. "
                         "Reload to see the latest list, then make your change again.")


class Invalid(ValueError):
    """The submitted list can't be saved. .problems = [{"row": index into the submitted rows, "message": ...}]."""

    def __init__(self, problems: list[dict]):
        super().__init__("; ".join(p["message"] for p in problems))
        self.problems = problems


def current(db: Session) -> VendorListState | None:
    return db.get(VendorListState, 1)


def current_version(db: Session) -> int:
    state = current(db)
    return state.version if state else 0


def active(db: Session) -> list[Vendor]:
    return list(db.scalars(select(Vendor).where(Vendor.is_active).order_by(func.lower(Vendor.party_name), Vendor.id)))


def status(db: Session) -> dict:
    state = current(db)
    total = db.scalar(select(func.count()).select_from(Vendor).where(Vendor.is_active))
    if state is None:
        return {"exists": False, "version": 0, "file_name": None, "updated_at": None, "updated_by": None, "total": 0}
    return {"exists": True, "version": state.version, "file_name": state.file_name, "updated_at": state.updated_at,
            "updated_by": state.updated_by, "total": total}


def _emails(email: str | None) -> frozenset[str]:
    """Order and case don't matter when comparing two addresses lists."""
    valid, invalid = split_emails(email)
    return frozenset(a.casefold() for a in valid) | frozenset(a.casefold() for a in invalid)


def _row(party_name: str, email: str | None) -> dict:
    return {"party_name": party_name, "email": email}


def diff(db: Session, rows: list[dict]) -> dict:
    """What replacing the stored list with these rows ({party_name, email, ...}) would change. Vendors are matched by
    name_key, the same key the matching engine uses. Writes nothing."""
    old = {name_key(v.party_name): v for v in active(db)}
    new = {name_key(r["party_name"]): r for r in rows}
    added = [_row(r["party_name"], r["email"]) for k, r in new.items() if k not in old]
    removed = [_row(v.party_name, v.email) for k, v in old.items() if k not in new]
    changed = [{"party_name": r["party_name"], "old_party_name": old[k].party_name, "old_email": old[k].email,
                "new_email": r["email"]}
               for k, r in new.items() if k in old
               and (_emails(old[k].email) != _emails(r["email"]) or old[k].party_name != r["party_name"])]
    return {"new": added, "removed": removed, "changed": changed,
            "unchanged": len(new) - len(added) - len(changed)}


def _bump(db: Session, base_version: int, user: str, file_name: str | None) -> VendorListState:
    """Move the list to base_version + 1, or raise Conflict. Doesn't commit."""
    now = config.now_ist()
    if base_version == 0:  # first-time setup: the PK makes two simultaneous first uploads collide
        try:
            state = VendorListState(id=1, version=1, file_name=file_name or "(entered in the app)", updated_at=now, updated_by=user)
            db.add(state)
            db.flush()
        except IntegrityError:
            db.rollback()
            raise Conflict(current(db)) from None
        return state
    values = {"version": base_version + 1, "updated_at": now, "updated_by": user}
    if file_name:
        values["file_name"] = file_name
    if not db.execute(update(VendorListState).where(VendorListState.id == 1, VendorListState.version == base_version)
                      .values(**values)).rowcount:
        db.expire_all()  # nothing was written by this call; the caller decides what to do with its own changes
        raise Conflict(current(db))
    db.expire_all()
    return current(db)


def _log(db: Session, state: VendorListState, user: str, action: str, file_name: str | None, changes: dict) -> None:
    db.add(VendorListHistory(
        version=state.version, user=user, action=action, file_name=file_name,
        vendor_count=db.scalar(select(func.count()).select_from(Vendor).where(Vendor.is_active)),
        added=len(changes["new"]), removed=len(changes["removed"]), changed=len(changes["changed"]),
        details={"added": [r["party_name"] for r in changes["new"]][:_DETAIL_CAP],
                 "removed": [r["party_name"] for r in changes["removed"]][:_DETAIL_CAP],
                 "changed": [r["party_name"] for r in changes["changed"]][:_DETAIL_CAP]}))


def _requeue(db: Session, vendor_ids: list[int]) -> int:
    """New or fixed vendors may unblock earlier exceptions (VENDOR_NOT_FOUND / INVALID_EMAIL): re-check and queue them.
    The list is already saved; a failure here is logged and never undoes it."""
    from app import reconcile  # here, not at the top: reconcile imports a lot, and this module is imported by ingest

    queued = 0
    for vendor_id in vendor_ids:
        try:
            queued += reconcile.requeue_vendor_exceptions(db, vendor_id)
        except Exception:
            db.rollback()
            log.exception("re-checking exceptions for vendor %s after a vendors list change failed", vendor_id)
    return queued


def replace(db: Session, rows: list[dict], file_name: str, user: str, base_version: int) -> dict:
    """Make the stored list exactly these rows (from an uploaded file, already parsed). New names are added, names that
    are not in the file are removed, and an existing vendor takes the file's email. Raises Conflict. Commits."""
    changes = diff(db, rows)
    if base_version == current_version(db) and base_version and not any(changes[k] for k in ("new", "removed", "changed")):
        return {"status": status(db), "requeued": 0}  # the file is the stored list: no new version, nothing to log
    state = _bump(db, base_version, user, file_name)
    everyone = {name_key(v.party_name): v for v in db.scalars(select(Vendor))}  # also the removed ones, to switch back on
    keep = {name_key(r["party_name"]) for r in rows}
    touched = []
    for r in rows:
        v = everyone.get(name_key(r["party_name"]))
        if v is None:
            v = Vendor(party_name=r["party_name"], email=r["email"], is_email_valid=r["is_email_valid"], pan=r["pan"])
            db.add(v)
        else:
            was_active, old = v.is_active, _emails(v.email)
            v.party_name, v.email, v.is_email_valid, v.is_active = r["party_name"], r["email"], r["is_email_valid"], True
            v.pan = r["pan"] or v.pan
            if was_active and old == _emails(r["email"]):
                continue
        touched.append(v)
    for k, v in everyone.items():
        if v.is_active and k not in keep:
            v.is_active = False
    _log(db, state, user, "UPLOAD", file_name, changes)
    db.commit()
    return {"status": status(db), "requeued": _requeue(db, [v.id for v in touched if v.is_email_valid])}


def check_rows(rows: list[dict]) -> list[dict]:
    """Rows from the edit table ({id?, party_name, email}) as clean rows, or Invalid with every problem found:
    an empty Party Name, an email that isn't one (or several) valid address(es), a Party Name used twice."""
    problems, clean, seen = [], [], {}
    for i, r in enumerate(rows):
        name = " ".join((r.get("party_name") or "").split())
        email = (r.get("email") or "").strip()
        if not name_key(name):
            problems.append({"row": i, "field": "party_name", "message": "Party Name can't be empty"})
            continue
        valid, bad = split_emails(email)
        if not email:
            problems.append({"row": i, "field": "email", "message": f"Email id is empty for {name}"})
        elif bad or not valid:
            problems.append({"row": i, "field": "email", "message": f"Not a valid email address for {name}: {', '.join(bad) or email}"})
        key = name_key(name)
        if key in seen:
            problems.append({"row": i, "field": "party_name", "message": f"{name} is listed twice (also row {seen[key] + 1})"})
        seen.setdefault(key, i)
        clean.append({"id": r.get("id"), "party_name": name, "email": ", ".join(dict.fromkeys(valid)), "is_email_valid": True})
    if not rows:
        problems.append({"row": 0, "field": "party_name", "message": "The list can't be empty"})
    if problems:
        raise Invalid(problems)
    return clean


def edit(db: Session, rows: list[dict], user: str, base_version: int) -> dict:
    """Save the edit table: rows with an id are updated, rows without one are added, stored vendors missing from the
    table are removed. Raises Invalid (nothing saved) or Conflict. Commits."""
    clean = check_rows(rows)
    stored = {v.id: v for v in db.scalars(select(Vendor).where(Vendor.is_active))}
    if unknown := [i for i, r in enumerate(clean) if r["id"] is not None and r["id"] not in stored]:
        raise Invalid([{"row": i, "message": "This vendor was removed meanwhile; reload the list"} for i in unknown])
    removed_ids = set(stored) - {r["id"] for r in clean}
    changes = {"new": [], "removed": [_row(stored[i].party_name, stored[i].email) for i in removed_ids], "changed": []}
    for r in clean:
        v = stored.get(r["id"])
        if v is None:
            changes["new"].append(r)
        elif v.party_name != r["party_name"] or _emails(v.email) != _emails(r["email"]):
            changes["changed"].append(r)
    if not any(changes.values()):
        return {"status": status(db), "requeued": 0}  # nothing changed: no new version

    state = _bump(db, base_version, user, None)
    stored = {v.id: v for v in db.scalars(select(Vendor).where(Vendor.is_active))}
    everyone = {name_key(v.party_name): v for v in db.scalars(select(Vendor))}
    touched = []
    for i in removed_ids:
        if i in stored:
            stored[i].is_active = False
    db.flush()  # a removed name freed up before another row takes it
    for r in clean:
        v = stored.get(r["id"])
        if v is None:  # added: a name that was removed earlier comes back as that same vendor
            v = everyone.get(name_key(r["party_name"]))
            if v is None:
                v = Vendor(party_name=r["party_name"])
                db.add(v)
        elif v.party_name == r["party_name"] and _emails(v.email) == _emails(r["email"]):
            continue
        elif (other := everyone.get(name_key(r["party_name"]))) is not None and other.id != v.id and not other.is_active:
            other.party_name = f"{other.party_name} [removed {other.id}]"  # frees the name for this vendor (names are UNIQUE)
            db.flush()
        v.party_name, v.email, v.is_email_valid, v.is_active = r["party_name"], r["email"], True, True
        touched.append(v)
        db.flush()
    _log(db, state, user, "EDIT", None, changes)
    db.commit()
    return {"status": status(db), "requeued": _requeue(db, [v.id for v in touched])}


def record_email_fix(db: Session, user: str, vendor: Vendor, old_email: str | None) -> None:
    """The Vendor emails / Exceptions "fix email" edit is a list change too: bump the version and log it. Doesn't commit.
    Not conflict-checked: it changes one vendor's email, and the last save of that one field wins, as it always did."""
    for _ in range(3):  # somebody saved the list in the same instant: take their version as the base and go again
        state = current(db)
        if state is None:  # no stored list (yet): nothing to version
            return
        try:
            state = _bump(db, state.version, user, None)
            break
        except Conflict:
            continue
    else:
        raise Conflict(current(db))
    _log(db, state, user, "EMAIL_FIX", None, {"new": [], "removed": [],
                                              "changed": [{"party_name": vendor.party_name, "old_email": old_email}]})


def history(db: Session, limit: int = 100) -> list[VendorListHistory]:
    return list(db.scalars(select(VendorListHistory).order_by(VendorListHistory.id.desc()).limit(limit)))
