"""Test helpers: turn a fixture module's source rows into uploaded files."""
import io

import pandas as pd


def xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def files_from(fixture) -> dict[str, tuple[str, bytes]]:
    """{kind: (file name, bytes)} from a fixture module's <KIND>_SOURCE lists, as ingest_batch takes them."""
    return {kind: (f"{kind}.xlsx", xlsx(getattr(fixture, f"{kind.upper()}_SOURCE")))
            for kind in ("consolidated", "bank", "gdn", "tds", "vendors")}
