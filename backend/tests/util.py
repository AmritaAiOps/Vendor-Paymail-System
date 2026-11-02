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
