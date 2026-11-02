"""Checks the app against the endpoint table (b) and function table (c) in docs/CONTRACT.md.
Shared, frozen. Both people run it before finishing any phase and after the merge."""
import importlib
import inspect
import re
from pathlib import Path

from app.main import app

CONTRACT = (Path(__file__).parents[3] / "docs" / "CONTRACT.md").read_text(encoding="utf-8")


def _rows(first_cell: str) -> list[list[str]]:
    """Markdown table rows whose first cell matches; cells split on unescaped pipes, backticks stripped."""
    rows = []
    for line in CONTRACT.splitlines():
        cells = [c.strip().strip("`").replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if cells and re.fullmatch(first_cell, cells[0]):
            rows.append(cells)
    return rows


def _short(sig: str) -> str:
    sig = re.sub(r"<class '([\w.]+)'>", r"\1", sig)
    return re.sub(r"\b(?:\w+\.)+(\w+)", r"\1", sig)  # sqlalchemy.orm.session.Session -> Session


def test_endpoints_match_contract():
    documented = {(m, p) for m, p, *_ in _rows("GET|POST|PUT|PATCH|DELETE")}
    actual = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert len(documented) == 23
    assert documented == actual, {"missing": documented - actual, "undocumented": actual - documented}


def test_functions_match_contract():
    rows = _rows(r"app(\.\w+)+")
    assert len(rows) == 12
    for module, name, sig, *_ in rows:
        fn = getattr(importlib.import_module(module), name, None)
        assert fn is not None, f"{module}.{name} missing"
        assert _short(str(inspect.signature(fn))) == sig, f"{module}.{name}"
