"""Value cleaners. Pure functions: raw cell in, clean value out; ValueError when a value can't be parsed.
These normalise what we store; the uploaded files themselves are never modified."""
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_XML_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")  # Excel's escape for control chars, e.g. _x000D_ = carriage return
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CENT = Decimal("0.01")

# Explicit formats instead of dateutil/pd.to_datetime(dayfirst=True), which reads 2026-08-01 as 8 Jan.
_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y",
                 "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y")


def clean_str(value) -> str | None:
    """Trim, collapse whitespace, drop zero-width/control chars, NBSP -> space. Blank -> None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = _XML_ESCAPE.sub(lambda m: chr(int(m[1], 16)), str(value))
    s = unicodedata.normalize("NFKC", s)  # NBSP and other compatibility spaces -> plain space
    s = "".join(" " if unicodedata.category(c) == "Cc" else c for c in s if unicodedata.category(c) != "Cf")
    return " ".join(s.split()) or None


def normalize_utr(value) -> str | None:
    s = clean_str(value)
    if s is None:
        return None
    s = s.upper().replace(" ", "")
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s  # numeric cell read as float: 504411.0


def parse_amount(value) -> Decimal | None:
    """'5,45,060.00', '4788', 1185.4999999 -> Decimal to 2 places. Blank -> None."""
    s = clean_str(value)
    if s is None:
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        d = Decimal(s.strip("()").replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        raise ValueError(f"not an amount: {s!r}") from None
    if not d.is_finite():
        raise ValueError(f"not an amount: {s!r}")
    d = d.quantize(_CENT, rounding=ROUND_HALF_UP)
    return -d if neg else d


def parse_date(value) -> date | None:
    """dd-mmm-yy, dd/mm/yyyy, ISO, datetime cells and Excel serial numbers. Blank -> None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = clean_str(value)
    if s is None:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):  # Excel serial day number
        return date(1899, 12, 30) + timedelta(days=int(float(s)))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"not a date: {s!r}")


_NAME_WORDS = {"private": "pvt", "limited": "ltd", "company": "co"}
_P_LTD = re.compile(r"\bp\b(?=[\s.)]*(?:ltd|limited)\b)")  # "P Ltd" / "P. Ltd" / "(P) Ltd" = Private Limited


def _name_text(name) -> str:
    return _P_LTD.sub("pvt", (clean_str(name) or "").casefold().replace("&", " and "))


def _name_words(name) -> list[str]:
    return [_NAME_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", re.sub(r"\{[^}]*\}", " ", _name_text(name)))]


def parse_pan(value) -> str | None:
    """The PAN in a PAN or a GSTIN cell (a GSTIN is 2-digit state + PAN + 3 more characters); None if it isn't one."""
    m = re.fullmatch(r"(?:\d{2})?([A-Z]{5}\d{4}[A-Z])(?:[0-9A-Z]Z[0-9A-Z])?", re.sub(r"\s+", "", str(value or "")).upper())
    return m.group(1) if m else None


def name_key(name) -> str:
    """Vendor-name match key: case, spaces and punctuation ignored, common suffixes unified, {codes} dropped.
    'R.K PHARMA' == 'R.K. Pharma'; 'A.C SURGIPHARMA PVT. LTD' == 'A.C Surgipharma Private Limited' == '... P Ltd'."""
    return "".join(_name_words(name))


_SUFFIX_WORDS = {"pvt", "private", "ltd", "limited", "llp", "co", "company", "the", "ms", "and"}


def bare_name_key(name) -> str:
    """name_key without company suffixes, (bracketed) text kept: 'AARK PHARMACEUTICALS PRIVATE LIMITED' ==
    'Aark Pharmaceuticals' but != 'Aark Pharmaceuticals (Neon Cfa)'. Picks among several loose matches."""
    return "".join(w for w in _name_words(name) if w not in _SUFFIX_WORDS)


def cfa_company_key(name) -> str | None:
    """The company a CFA entry forwards for, as a loose key: 'Bansal Medical Hall (Macleods Cfa)' -> 'macleods'.
    None unless the name has a '(<company> CFA)' bracket."""
    m = re.search(r"\(([^()]*?)\bc\.?\s*f\.?\s*a\.?\s*\)", (clean_str(name) or "").casefold())
    return loose_name_key(m.group(1)) or None if m else None


def loose_name_key(name) -> str:
    """Looser key for a second-try vendor match: also drops (bracketed) and {braced} text and company suffixes.
    'PHARMAGIX' == 'Pharmagix(A Unit Of White Pharmaceuticals)'. It can merge distinct vendors (a company and its
    CFA), so only use it when exactly one vendor matches."""
    s = re.sub(r"^m/s\b", " ", _name_text(name))  # "M/S VALTURE ..." = Messrs
    s = re.sub(r"[({][^)}]*[)}]?", " ", s)
    # "MANKIND PHARMA LIMITED DL": a trailing branch location. ponytail: Delhi only, add other states as they show up
    s = re.sub(r"\b(?:dl|delhi)\W*$", " ", s)
    s = re.sub(r"\s-+\s*cfa\b.*$", " ", s)  # "Varenyam Healthcare - Cfa", "Win Medicare ... - Cfa Delhi"
    s = re.sub(r"['’]s\b", "s", s)  # "Dr. Reddy's" == "DR. REDDYS", "Trader'S" == "TRADERS"
    # plural "s" dropped: 'N.R.I. HEALTH AIDS' == 'Nri Health Aid', 'Chemical' == 'Chemicals'
    return "".join(w[:-1] if len(w) > 3 and w.endswith("s") else w
                   for w in re.findall(r"[a-z0-9]+", s) if w not in _SUFFIX_WORDS)


def split_emails(value) -> tuple[list[str], list[str]]:
    """'a@x.com; b@y.com', 'a / b', "'Name' <a@x.com>", 'a@x.com>' -> (valid, invalid) addresses."""
    s = clean_str(value)
    if s is None:
        return [], []
    valid, invalid = [], []
    for part in re.split(r"[;,/]", s):
        if found := _EMAIL.search(part):  # tolerates display names, quotes and stray <>
            valid.append(found[0])
        elif part.strip():
            invalid.append(part.strip())
    return valid, invalid
