"""Special cases for the reconciliation engine (Phase 3). Shared, frozen once agreed. Every value is SAMPLE.

One batch with 24 invoices, each exercising one rule. Source rows use the real column headers.
EXPECTED is keyed by (invoice no, UTR) because two vendors share the generic invoice no "4708"."""
from datetime import date
from decimal import Decimal as D

PAID = "16/09/2025"  # bank value date of every payment
PAID_ON = date(2025, 9, 16)


def utr(n: int) -> str:
    return f"DLXBH900000000{n:02d}"


def _cons(inv, vendor, invoice, paid, utr_):
    return {"benefName": vendor, "Narration 2- Invoice No": inv, "Narration 3- PO No": None, "GRN NO:": None,
            "Invoice Amount": invoice, "Cheque Amount": paid, "Debit Note": None, "Diff": None,
            "Transaction Date": "2025-09-16 00:00:00", "UTR NO:": utr_}


def _bank(utr_, vendor, debit, credit="0.00", description=None):
    return {"Txn Date": PAID, "Description": description or f"NEFT DR-{utr_}-{vendor}-HDFC0000001-CPC- PS AND TF",
            "Value Date": PAID, "Ref / Cheque No": utr_, "Credit": credit, "Debit": debit, "Balance": "xxxxxxx"}


VENDORS_SOURCE = [
    {"Vendor\nName": "Sunrise Pharma", "Email ID": "accounts@sunrise.example"},
    {"Vendor\nName": "Kiran Medicos", "Email ID": "accounts@kiran.example"},
    {"Vendor\nName": "Orbit Healthcare", "Email ID": "accounts@orbit.example"},
    {"Vendor\nName": "R.K. Pharma", "Email ID": "accounts@rkpharma.example"},  # consolidated says "R.K PHARMA"
    {"Vendor\nName": "Harkrishan Medicals", "Email ID": "harkrishan,medicals@gmail.com"},  # invalid on purpose
    {"Vendor\nName": "Zenith Remedies(A Unit Of Zen Labs)", "Email ID": "accounts@zenith.example"},
    {"Vendor\nName": "Nova Labs", "Email ID": "accounts@novalabs.example"},       # a company...
    {"Vendor\nName": "Nova Labs (Cfa)", "Email ID": "cfa@novalabs-cfa.example"},  # ...and its CFA
]

CONSOLIDATED_SOURCE = [
    _cons("INV-S01", "SUNRISE PHARMA", "100000", "94900", utr(1)),      # TDS 100 + deduction 5,000
    _cons("INV-S02", "KIRAN MEDICOS", "50000", "49990", utr(2)),        # TDS 50 > shortfall 10
    _cons("INV-S03", "ORBIT HEALTHCARE", "10000.5", "10000", utr(3)),   # 0.50 short: rounding
    _cons("INV-S04", "ORBIT HEALTHCARE", "10001", "10000", utr(4)),     # exactly 1.00 short: rounding
    _cons("INV-S05", "ORBIT HEALTHCARE", "10001.01", "10000", utr(5)),  # 1.01 short: real, no reason
    _cons("INV-S06", "R.K PHARMA", "23000", "20000", utr(6)),           # name variant; 3,000 short, no reason
    _cons("INV-S07", "HARKRISHAN MEDICALS", "5000", "5000", utr(7)),    # invalid email
    _cons("INV-S08", "UNKNOWN TRADERS", "7000", "7000", utr(8)),        # not in vendor list
    _cons("INV-S09", "SUNRISE PHARMA", "8000", "8000", utr(9)),         # UTR not in bank statement
    _cons("INV-S10", "SUNRISE PHARMA", "10000", "10000", utr(10)),      # duplicate amount, same vendor, same day...
    _cons("INV-S11", "SUNRISE PHARMA", "10000", "10000", utr(11)),      # ...stays a separate result
    _cons("INV-S12", "SUNRISE PHARMA", "6000", "6000", None),           # blank UTR
    _cons("INV-S13", "KIRAN MEDICOS", "4725", "4725", utr(13)),         # bounced (NEFT RETURN)
    _cons("INV-S14", "ORBIT HEALTHCARE", "18336", "10201", utr(14)),    # TDS listed but not cut; GDN explains all
    _cons("INV-S15", "ORBIT HEALTHCARE", "158153", "152520", utr(15)),  # GDN 47 doesn't explain 5,633
    _cons("INV-S16", "KIRAN MEDICOS", "398", "428", utr(16)),           # overpaid by 30
    _cons("INV-S17", "KIRAN MEDICOS", "545580", "545060", utr(17)),     # TDS 519.60 vs shortfall 520: rounding
    _cons("INV-S18", "SUNRISE PHARMA", "50000", "49950", utr(18)),      # TDS file spells vendor differently
    _cons("4708", "SUNRISE PHARMA", "10100", "10000", utr(19)),         # generic invoice no: no fallback match
    _cons("4708", "KIRAN MEDICOS", "2000", "2000", utr(20)),            # same generic invoice no, other vendor
    _cons("INV-S21", "ORBIT HEALTHCARE", "30000", "27000", utr(21)),    # two debit notes on one invoice
    _cons("INV-S22", "KIRAN MEDICOS", "12000", "11000", utr(22)),       # debit note amount matches, narration blank
    _cons("INV-S23", "ZENITH REMEDIES PRIVATE LIMITED", "9000", "9000", utr(23)),  # list adds "(A Unit Of ...)"
    _cons("INV-S24", "NOVA LABS PVT LTD", "9000", "9000", utr(24)),     # matches both Nova Labs entries: ambiguous
]

BANK_SOURCE = [
    _bank(utr(1), "SUNRISE PHARMA", "94,900.00"),
    _bank(utr(2), "KIRAN MEDICOS", "49,990.00"),
    _bank(utr(3), "ORBIT HEALTHCARE", "10,000.00"),
    _bank(utr(4), "ORBIT HEALTHCARE", "10,000.00"),
    _bank(utr(5), "ORBIT HEALTHCARE", "10,000.00"),
    _bank(utr(6), "R.K PHARMA", "20,000.00"),
    _bank(utr(7), "HARKRISHAN MEDICALS", "5,000.00"),
    _bank(utr(8), "UNKNOWN TRADERS", "7,000.00"),
    _bank(utr(10), "SUNRISE PHARMA", "10,000.00"),
    _bank(utr(11), "SUNRISE PHARMA", "10,000.00"),
    _bank(utr(13), "KIRAN MEDICOS", "4,725.00"),
    _bank(utr(14), "ORBIT HEALTHCARE", "10,201.00"),
    _bank(utr(15), "ORBIT HEALTHCARE", "1,52,520.00"),
    _bank(utr(16), "KIRAN MEDICOS", "428.00"),
    _bank(utr(17), "KIRAN MEDICOS", "5,45,060.00"),
    _bank(utr(18), "SUNRISE PHARMA", "49,950.00"),
    _bank(utr(19), "SUNRISE PHARMA", "10,000.00"),
    _bank(utr(20), "KIRAN MEDICOS", "2,000.00"),
    _bank(utr(21), "ORBIT HEALTHCARE", "27,000.00"),
    _bank(utr(22), "KIRAN MEDICOS", "11,000.00"),
    _bank(utr(23), "ZENITH REMEDIES PRIVATE LIMITED", "9,000.00"),
    _bank(utr(24), "NOVA LABS PVT LTD", "9,000.00"),
    _bank("INDBN52025091600000013", "KIRAN MEDICOS", "0.00", credit="4,725.00",
          description=f"NEFT RETURN-PAYMENT STOPPED-KIRAN MEDICOS-{utr(13)}"),
]

TDS_SOURCE = [
    {"PARTY NAME": "SUNRISE PHARMA", "Inv No": "INV-S01", "Inv Date": None, "TDS": "100"},
    {"PARTY NAME": "KIRAN MEDICOS", "Inv No": "INV-S02", "Inv Date": None, "TDS": "50"},
    {"PARTY NAME": "ORBIT HEALTHCARE", "Inv No": "INV-S14", "Inv Date": None, "TDS": "351"},
    {"PARTY NAME": "KIRAN MEDICOS", "Inv No": "INV-S17", "Inv Date": None, "TDS": "519.6"},
    {"PARTY NAME": "SUNRISE PHARMACEUTICALS", "Inv No": "INV-S18", "Inv Date": None, "TDS": "50"},
    {"PARTY NAME": "MEDLINE AGENCIES", "Inv No": "4708", "Inv Date": None, "TDS": "100"},
]

GDN_SOURCE = [
    {"Date": "2025-09-10 00:00:00", "Particulars": "Sunrise Pharma", "Voucher No.": "501",
     "Voucher Ref. No.": "INV-S01", "Narration": "Short supply (DN-0501)", "Gross Total": "5000"},
    {"Date": "2025-09-10 00:00:00", "Particulars": "Orbit Healthcare", "Voucher No.": "612",
     "Voucher Ref. No.": "INV-S14", "Narration": "Expired goods returned (DN-0612)", "Gross Total": "8135"},
    {"Date": "2025-09-10 00:00:00", "Particulars": "Orbit Healthcare", "Voucher No.": "613",
     "Voucher Ref. No.": "INV-S15", "Narration": "Rate difference (DN-0613)", "Gross Total": "47"},
    {"Date": "2025-09-10 00:00:00", "Particulars": "Orbit Healthcare", "Voucher No.": "701",
     "Voucher Ref. No.": "INV-S21", "Narration": "Breakage (DN-0701)", "Gross Total": "1000"},
    {"Date": "2025-09-11 00:00:00", "Particulars": "Orbit Healthcare", "Voucher No.": "702",
     "Voucher Ref. No.": "INV-S21", "Narration": "Short expiry (DN-0702)", "Gross Total": "2000"},
    {"Date": "2025-09-11 00:00:00", "Particulars": "Kiran Medicos", "Voucher No.": "722",
     "Voucher Ref. No.": "INV-S22", "Narration": None, "Gross Total": "1000"},
]


def _x(status, exception_type=None, tds=None, deduction=None, reason=None):
    return {"status": status, "exception_type": exception_type, "tds_amount": tds, "invoice_deduction": deduction,
            "reason": reason}


EXPECTED = {
    ("INV-S01", utr(1)): _x("DEDUCTION", tds=D("100.00"), deduction=D("5000.00"), reason="Short supply (DN-0501)"),
    ("INV-S02", utr(2)): _x("MANUAL_REVIEW", "AMOUNT_MISMATCH", tds=D("50.00")),
    ("INV-S03", utr(3)): _x("PAID_IN_FULL"),
    ("INV-S04", utr(4)): _x("PAID_IN_FULL"),
    ("INV-S05", utr(5)): _x("MANUAL_REVIEW", "REASON_MISSING", deduction=D("1.01")),
    ("INV-S06", utr(6)): _x("MANUAL_REVIEW", "REASON_MISSING", deduction=D("3000.00")),
    ("INV-S07", utr(7)): _x("EXCEPTION", "INVALID_EMAIL"),
    ("INV-S08", utr(8)): _x("EXCEPTION", "VENDOR_NOT_FOUND"),
    ("INV-S09", utr(9)): _x("EXCEPTION", "UTR_NOT_FOUND"),
    ("INV-S10", utr(10)): _x("PAID_IN_FULL"),
    ("INV-S11", utr(11)): _x("PAID_IN_FULL"),
    ("INV-S12", None): _x("EXCEPTION", "UTR_NOT_FOUND"),
    ("INV-S13", utr(13)): _x("EXCEPTION", "BOUNCED"),
    ("INV-S14", utr(14)): _x("DEDUCTION", deduction=D("8135.00"), reason="Expired goods returned (DN-0612)"),
    ("INV-S15", utr(15)): _x("MANUAL_REVIEW", "AMOUNT_MISMATCH", deduction=D("5633.00")),
    ("INV-S16", utr(16)): _x("MANUAL_REVIEW", "AMOUNT_MISMATCH"),
    ("INV-S17", utr(17)): _x("TDS_ONLY", tds=D("519.60")),
    ("INV-S18", utr(18)): _x("TDS_ONLY", tds=D("50.00")),
    ("4708", utr(19)): _x("MANUAL_REVIEW", "REASON_MISSING", deduction=D("100.00")),
    ("4708", utr(20)): _x("PAID_IN_FULL"),
    ("INV-S21", utr(21)): _x("DEDUCTION", deduction=D("3000.00"), reason="Breakage (DN-0701); Short expiry (DN-0702)"),
    ("INV-S22", utr(22)): _x("MANUAL_REVIEW", "REASON_MISSING", deduction=D("1000.00")),
    ("INV-S23", utr(23)): _x("PAID_IN_FULL"),
    ("INV-S24", utr(24)): _x("EXCEPTION", "VENDOR_NOT_FOUND"),  # never guess between a company and its CFA
}
