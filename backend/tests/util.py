"""Test helpers: turn a fixture module's source rows into uploaded files."""
import io

from openpyxl import Workbook


def xlsx(rows: list[dict]) -> bytes:
    """One sheet: a header row (every key, first-seen order), then the rows. Missing keys are empty cells."""
    headers = list(dict.fromkeys(k for r in rows for k in r))
    wb = Workbook()
    wb.active.append(headers)
    for r in rows:
        wb.active.append([r.get(h) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def files_from(fixture) -> dict[str, tuple[str, bytes]]:
    """{kind: (file name, bytes)} from a fixture module's <KIND>_SOURCE lists, as ingest_batch takes them."""
    return {kind: (f"{kind}.xlsx", xlsx(getattr(fixture, f"{kind.upper()}_SOURCE")))
            for kind in ("consolidated", "bank", "gdn", "tds", "vendors")}


def seed_list(client, files) -> None:
    """Store files["vendors"] as the vendors list through the API (the batch upload no longer takes one)."""
    version = client.get("/api/vendor-list").json()["version"]
    r = client.post("/api/vendor-list/replace", files={"file": files["vendors"]}, data={"base_version": version})
    assert r.status_code == 200, r.text


def post_batch(client, files, **kw):
    """POST /api/batches with the four per-run files, after storing the fixture's vendors list."""
    seed_list(client, files)
    return client.post("/api/batches", files={k: v for k, v in files.items() if k != "vendors"}, **kw)


def ingest(db, fixture):
    """Store the fixture's vendors list, then ingest its four per-run files. Returns the batch."""
    from app import vendor_list
    from app.ingest import ingest_batch, parse_vendors_file

    files = files_from(fixture)
    rows, _ = parse_vendors_file(files["vendors"][1], files["vendors"][0])
    vendor_list.replace(db, rows, files["vendors"][0], "tester@example.com", vendor_list.status(db)["version"])
    return ingest_batch(db, {k: v for k, v in files.items() if k != "vendors"})
