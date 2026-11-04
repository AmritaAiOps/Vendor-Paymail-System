"""Parse the five input files and store the cleaned rows under an upload batch. Owner: Person A.

Each file goes: bytes -> _read_rows (find the header row on every sheet, map columns) -> _parse_<kind>
(clean each row; reject bad rows with a reason) -> rows ready to insert. Uploaded files are only read."""
import hashlib
import io
import json
import re
from typing import BinaryIO

import openpyxl
import xlrd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.contract import BatchStatus, GdnRow
from app.ingest.clean import clean_str, name_key, normalize_utr, parse_amount, parse_date, parse_pan, split_emails
from app.ingest.columns import COLUMNS, REQUIRED
from app.models import BankTransaction, ConsolidatedEntry, GdnRecord, TdsRecord, UploadBatch, Vendor

FILE_KINDS = ("consolidated", "bank", "gdn", "tds", "vendors")
_NEFT = re.compile(r"^NEFT DR-[A-Z0-9]+-(.+)-([A-Z]{4}0[A-Z0-9]{6})-")  # NEFT DR-<utr>-<name>-<ifsc>-...


class FileError(ValueError):
    """One or more files can't be used. .problems = [{"file": kind, "message": ...}]."""

    def __init__(self, problems: list[dict]):
        super().__init__("; ".join(f"{p['file']}: {p['message']}" for p in problems))
        self.problems = problems


def _norm(header) -> str:
    return re.sub(r"[^a-z0-9]", "", (clean_str(header) or "").casefold())


def _label(kind: str, field: str) -> str:
    return f'"{COLUMNS[kind][field][0]}"'


# Read as an empty cell: pandas.read_excel's default NA strings (the vendor list writes "NA" for no contact 2)
# plus Excel's error values.
_EMPTY = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN", "<NA>", "N/A",
          "NA", "NULL", "NaN", "None", "n/a", "nan", "null", "#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NAME?", "#NULL!"}


def _text(v) -> str | None:
    """One cell as text, None if empty. Whole numbers lose their ".0" and datetimes read "2026-08-01 00:00:00":
    the same text pandas.read_excel(dtype=str) gave, which ingest was built and tested against."""
    if v is None or (isinstance(v, str) and v in _EMPTY):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def _sheets(data: bytes) -> dict[str, list[list[str | None]]]:
    """Every sheet as rows of cell text. Legacy .xls through xlrd, .xlsx through openpyxl (cached formula values)."""
    if data.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2: legacy .xls
        book = xlrd.open_workbook(file_contents=data)
        cell = lambda c: (xlrd.xldate_as_datetime(c.value, book.datemode) if c.ctype == xlrd.XL_CELL_DATE
                          else None if c.ctype == xlrd.XL_CELL_ERROR else c.value)
        return {s.name: [[_text(cell(c)) for c in s.row(i)] for i in range(s.nrows)] for s in book.sheets()}
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        return {ws.title: [[_text(v) for v in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    finally:
        wb.close()


def _find_header(rows: list[list], kind: str) -> tuple[int | None, dict | list]:
    """(row index, {field: column index}) for the first of the top 10 rows holding every required header,
    else (None, the required fields missing from the closest row)."""
    best = REQUIRED[kind]
    for i in range(min(10, len(rows))):
        headers = [_norm(h) for h in rows[i]]
        cols = {}
        for field, aliases in COLUMNS[kind].items():
            hit = next((headers.index(_norm(a)) for a in aliases if _norm(a) in headers), None)
            if hit is not None:
                cols[field] = hit
        missing = [f for f in REQUIRED[kind] if f not in cols]
        if not missing:
            return i, cols
        best = min(best, missing, key=len)
    return None, best


def detect_kind(data: bytes) -> str | None:
    """Which of FILE_KINDS this workbook is, by its headers; None if unreadable or if zero or several kinds fit."""
    try:
        sheets = _sheets(data).values()
    except Exception:  # protected or corrupt: the caller falls back to the file name
        return None
    fits = [k for k in FILE_KINDS if any(_find_header(rows, k)[0] is not None for rows in sheets)]
    return fits[0] if len(fits) == 1 else None


def _read_rows(data: bytes, kind: str) -> list[tuple[str, int, dict]]:
    """Data rows of every sheet that has the required headers, as (sheet, excel row, {field: raw value}).
    Sheets without them (e.g. a TOTAL sheet) are ignored. FileError if no sheet has them."""
    try:
        sheets = _sheets(data)
    except Exception as e:  # xlrd/openpyxl raise many types for corrupt or protected files
        raise FileError([{"file": kind, "message": f"can't be read as an Excel file ({type(e).__name__})"}]) from None
    rows, missing = [], REQUIRED[kind]
    for sheet, cells in sheets.items():
        header, cols = _find_header(cells, kind)
        if header is None:
            missing = min(missing, cols, key=len)
            continue
        missing = []
        rows += [(sheet, i + 1, {f: cells[i][c] if c < len(cells[i]) else None for f, c in cols.items()})
                 for i in range(header + 1, len(cells))]
    if missing:
        names = ", ".join(_label(kind, f) for f in missing)
        raise FileError([{"file": kind, "message": f"missing column(s) {names}"}])
    return rows


def _new_report(file_name: str) -> dict:
    return {"file_name": file_name, "rows_read": 0, "rows_kept": 0, "rows_skipped": 0, "rows_rejected": 0, "issues": []}


def _issue(report: dict, sheet: str, row: int, message: str, rejected: bool = True) -> None:
    report["issues"].append({"sheet": sheet, "row": row, "message": message, "rejected": rejected})
    report["rows_rejected"] += rejected


def _field(kind: str, raw: dict, field: str, parse=clean_str, required: bool = False):
    try:
        value = parse(raw.get(field))
    except ValueError as e:
        raise ValueError(f"{_label(kind, field)}: {e}") from None
    if value is None and required:
        raise ValueError(f"{_label(kind, field)} is empty")
    return value


def _each_row(kind: str, rows: list, report: dict):
    """Yield (sheet, row, raw) for non-blank rows, counting them as read."""
    for sheet, n, raw in rows:
        if any(clean_str(v) is not None for v in raw.values()):
            report["rows_read"] += 1
            yield sheet, n, raw


def _parse_consolidated(rows: list, report: dict) -> list[dict]:
    out, seen = [], set()
    for sheet, n, raw in _each_row("consolidated", rows, report):
        f = lambda field, parse=clean_str, required=False: _field("consolidated", raw, field, parse, required)
        try:
            utr, invoice_no = f("utr", normalize_utr), f("invoice_no")
            if utr is None and invoice_no is None:  # totals / filler rows at the bottom of the sheet
                report["rows_skipped"] += 1
                continue
            if utr in seen:
                raise ValueError(f"duplicate UTR {utr} in this file")
            row = {"utr": utr, "invoice_no": f("invoice_no", required=True), "vendor_name": f("vendor_name", required=True),
                   "po_no": f("po_no"), "grn_no": f("grn_no"),
                   "invoice_amount": f("invoice_amount", parse_amount, True),
                   "cheque_amount": f("cheque_amount", parse_amount, True),
                   "debit_note": f("debit_note", parse_amount), "diff": f("diff", parse_amount),
                   "transaction_date": f("transaction_date", parse_date)}
        except ValueError as e:
            _issue(report, sheet, n, str(e))
            continue
        if utr:
            seen.add(utr)
        out.append(row)
    return out


def _parse_bank(rows: list, report: dict) -> list[dict]:
    """Debit rows only. A credit whose description says RETURN (e.g. "NEFT RETURN-PAYMENT STOPPED-<name>-<utr>")
    marks the debit with that UTR as bounced."""
    out, returns = [], []
    for sheet, n, raw in _each_row("bank", rows, report):
        f = lambda field, parse=clean_str, required=False: _field("bank", raw, field, parse, required)
        try:
            debit, description = f("debit", parse_amount), f("description")
            if not debit or debit < 0:  # credit rows: money coming in
                report["rows_skipped"] += 1
                if "RETURN" in (description or "").upper():
                    returns.append((sheet, n, description))
                continue
            neft = _NEFT.match(description or "")
            out.append({"value_date": f("value_date", parse_date, True), "utr": f("utr", normalize_utr, True),
                        "debit": debit, "description": description,
                        "vendor_name": neft[1].strip() if neft else None, "ifsc": neft[2] if neft else None,
                        "is_bounced": False, "bounce_note": None})
        except ValueError as e:
            _issue(report, sheet, n, str(e))
    by_utr = {r["utr"]: r for r in out}
    for sheet, n, description in returns:
        hits = [by_utr[t] for t in re.findall(r"[A-Z0-9]{8,}", description.upper()) if t in by_utr]
        for hit in hits:
            hit.update(is_bounced=True, bounce_note=description)
            _issue(report, sheet, n, f"payment {hit['utr']} bounced: {description}", rejected=False)
        if not hits:
            _issue(report, sheet, n, f"return of a payment not in this statement: {description}", rejected=False)
    return out


def _parse_gdn(rows: list, report: dict) -> list[dict]:
    out = []
    for sheet, n, raw in _each_row("gdn", rows, report):
        f = lambda field, parse=clean_str, required=False: _field("gdn", raw, field, parse, required)
        try:
            if (f("vendor_name") or "").lower() in ("total", "grand total"):  # each month sheet ends with a totals row
                report["rows_skipped"] += 1
                continue
            out.append({"vendor_name": f("vendor_name", required=True), "invoice_no": f("invoice_no"),
                        "voucher_no": f("voucher_no"), "gdn_date": f("gdn_date", parse_date),
                        "amount": f("amount", parse_amount), "reason": f("reason"), "pan": f("pan", parse_pan)})
        except ValueError as e:
            _issue(report, sheet, n, str(e))
    return out


def _parse_tds(rows: list, report: dict) -> list[dict]:
    out = []
    for sheet, n, raw in _each_row("tds", rows, report):
        f = lambda field, parse=clean_str, required=False: _field("tds", raw, field, parse, required)
        try:
            if f("vendor_name") is None and f("invoice_no") is None:  # totals row
                report["rows_skipped"] += 1
                continue
            out.append({"vendor_name": f("vendor_name", required=True), "invoice_no": f("invoice_no", required=True),
                        "invoice_date": f("invoice_date", parse_date),
                        "tds_amount": f("tds_amount", parse_amount, True), "pan": f("pan", parse_pan)})
        except ValueError as e:
            _issue(report, sheet, n, str(e))
    return out


def _parse_vendors(rows: list, report: dict) -> list[dict]:
    """One row per party name (matched by name_key, across all sheets). Contact 1 and contact 2 are both mailed. A later duplicate only fills in a valid
    email the first one lacked. If any part of an email cell doesn't parse, the vendor keeps the original text
    and is_email_valid=False: a typo like 'harkrishan,medicals@gmail.com' must not become medicals@gmail.com."""
    by_name = {}
    for sheet, n, raw in _each_row("vendors", rows, report):
        try:
            name = _field("vendors", raw, "party_name", required=True)
        except ValueError as e:
            _issue(report, sheet, n, str(e))
            continue
        pan = parse_pan(raw.get("pan"))
        valid, invalid = split_emails(raw.get("email"))
        if invalid or not valid:
            _issue(report, sheet, n, f"email needs checking for {name}: {clean_str(raw.get('email'))}", rejected=False)
            vendor = {"party_name": name, "email": clean_str(raw.get("email")), "is_email_valid": False, "pan": pan}
        else:
            extra, bad = split_emails(raw.get("email_2"))
            if bad:  # same rule: a contact-2 cell that doesn't fully parse is not guessed at
                _issue(report, sheet, n, f"contact 2 email ignored for {name}: {clean_str(raw.get('email_2'))}",
                       rejected=False)
                extra = []
            vendor = {"party_name": name, "email": ", ".join(dict.fromkeys(valid + extra)), "is_email_valid": True, "pan": pan}
        prev = by_name.get(name_key(name))
        if prev is None:
            by_name[name_key(name)] = vendor
        else:
            report["rows_skipped"] += 1
            prev["pan"] = prev["pan"] or vendor["pan"]
            if vendor["is_email_valid"] and not prev["is_email_valid"]:
                prev.update(email=vendor["email"], is_email_valid=True)
    return list(by_name.values())


_PARSERS = {"consolidated": _parse_consolidated, "bank": _parse_bank, "gdn": _parse_gdn,
            "tds": _parse_tds, "vendors": _parse_vendors}


def _parse(kind: str, data: bytes, file_name: str) -> tuple[list[dict], dict]:
    report = _new_report(file_name)
    rows = _PARSERS[kind](_read_rows(data, kind), report)
    if not rows:
        raise FileError([{"file": kind, "message": "no usable rows"}])
    report["rows_kept"] = len(rows)
    return rows, report


def load_gdn_file(file: BinaryIO) -> list[GdnRow]:
    """Parse a GDN Report workbook (all month sheets) into rows. ValueError if the file isn't a GDN Report."""
    rows, _ = _parse("gdn", file.read(), "")
    return [GdnRow(**{k: v for k, v in r.items() if k != "pan"}) for r in rows]  # GdnRow is a frozen contract: no pan


class DuplicateUpload(Exception):
    """Files with exactly the same rows were uploaded before, as batch_id."""

    def __init__(self, batch_id: int):
        super().__init__(batch_id)
        self.batch_id = batch_id


def rows_sha256(parsed: dict[str, list[dict]]) -> str:
    """Fingerprint of the parsed rows, not the file bytes: re-saving the same workbook changes its bytes, not its rows."""
    return hashlib.sha256(json.dumps([parsed[k] for k in FILE_KINDS], sort_keys=True, default=str).encode()).hexdigest()


def ingest_batch(db: Session, files: dict[str, tuple[str, bytes]]) -> UploadBatch:
    """files = {kind: (file name, bytes)} for all five kinds. Raises DuplicateUpload if the same five files were
    uploaded before (same rows). Parses everything first; if any file is unusable, raises FileError listing every problem and
    stores nothing. Otherwise stores the batch and its rows, commits."""
    parsed, reports, problems = {}, {}, []
    for kind in FILE_KINDS:
        name, data = files[kind]
        try:
            parsed[kind], reports[kind] = _parse(kind, data, name)
        except FileError as e:
            problems += e.problems
    if problems:
        raise FileError(problems)
    digest = rows_sha256(parsed)
    if (earlier := db.scalar(select(UploadBatch.id).where(UploadBatch.files_sha256 == digest).limit(1))) is not None:
        raise DuplicateUpload(earlier)

    batch = UploadBatch(status=BatchStatus.UPLOADED, ingest_report=reports, files_sha256=digest,
                        **{f"{kind}_file": files[kind][0][:255] for kind in FILE_KINDS})
    db.add(batch)
    db.flush()
    for model, kind in ((ConsolidatedEntry, "consolidated"), (BankTransaction, "bank"),
                        (GdnRecord, "gdn"), (TdsRecord, "tds")):
        db.execute(insert(model), [{**r, "batch_id": batch.id} for r in parsed[kind]])
    _upsert_vendors(db, parsed["vendors"])
    db.commit()
    return batch


def _upsert_vendors(db: Session, vendors: list[dict]) -> None:
    """Vendors are global, not per batch. New names are added. An existing vendor's email is only filled in
    when it has no valid one, so an email fixed on the vendors page is never overwritten by an upload."""
    existing = {name_key(v.party_name): v for v in db.scalars(select(Vendor))}
    for row in vendors:
        v = existing.get(name_key(row["party_name"]))
        if v is None:
            db.add(Vendor(**row))
        else:
            v.pan = v.pan or row["pan"]
            if row["is_email_valid"] and not v.is_email_valid:
                v.email, v.is_email_valid = row["email"], True
