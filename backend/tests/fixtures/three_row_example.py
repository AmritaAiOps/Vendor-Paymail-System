"""The shared three-row example. Shared, frozen at foundation-v1.

Given by the specification: vendor, email, invoice numbers, amounts, the reason,
UTRs DLXBH25252000123 / DLXBH25252000188 and dates 12-Sep-25 / 15-Sep-25.
Everything else is invented and marked SAMPLE: INV-2310's UTR and dates, PO/GRN numbers,
voucher numbers, GDN/TDS dates, file names.

Source rows use the real column headers and look like pandas read_excel(dtype=str) output.
"""
from datetime import date
from decimal import Decimal

VENDOR = {"party_name": "ABC Pharma Distributors", "email": "accounts@abcpharma.example"}

FILE_NAMES = {  # SAMPLE
    "consolidated_file": "consolidated_sep25.xlsx",
    "bank_file": "bank_statement_sep25.xls",
    "gdn_file": "gdn_report_sep25.xlsx",
    "tds_file": "tds_194q_sep25.xlsx",
    "vendors_file": "vendor_contact_list.xlsx",
}

# ---- source rows, one list per input file ----

CONSOLIDATED_SOURCE = [
    {"benefName": "ABC PHARMA DISTRIBUTORS", "Narration 2- Invoice No": "INV-2305",
     "Narration 3- PO No": "SE/PH/2025-26/0901", "GRN NO:": "SE/PH/GRN/25/3101",  # SAMPLE PO/GRN
     "Invoice Amount": "120000", "Cheque Amount": "120000", "Debit Note": "0", "Diff": "0",
     "Transaction Date": "2025-09-12 00:00:00", "UTR NO:": "DLXBH25252000123"},
    {"benefName": "ABC PHARMA DISTRIBUTORS", "Narration 2- Invoice No": "INV-2310",
     "Narration 3- PO No": "SE/PH/2025-26/0907", "GRN NO:": "SE/PH/GRN/25/3110",  # SAMPLE PO/GRN
     "Invoice Amount": "200000", "Cheque Amount": "196000", "Debit Note": "4000", "Diff": "4000",
     "Transaction Date": "2025-09-12 00:00:00",  # SAMPLE date
     "UTR NO:": "DLXBH25252000150"},  # SAMPLE UTR
    {"benefName": "ABC PHARMA DISTRIBUTORS", "Narration 2- Invoice No": "INV-2291",
     "Narration 3- PO No": "SE/PH/2025-26/0876", "GRN NO:": "SE/PH/GRN/25/3050",  # SAMPLE PO/GRN
     "Invoice Amount": "545060", "Cheque Amount": "525060", "Debit Note": "20000", "Diff": "20000",
     "Transaction Date": "2025-09-15 00:00:00", "UTR NO:": "DLXBH25252000188"},
]

BANK_SOURCE = [  # debit side; amounts in Indian format
    {"Txn Date": "12/09/2025", "Description": "NEFT DR-DLXBH25252000123-ABC PHARMA DISTRIBUTORS",
     "Value Date": "12/09/2025", "Ref / Cheque No": "DLXBH25252000123",
     "Credit": "0.00", "Debit": "1,20,000.00", "Balance": "xxxxxxx"},
    {"Txn Date": "12/09/2025", "Description": "NEFT DR-DLXBH25252000150-ABC PHARMA DISTRIBUTORS",  # SAMPLE
     "Value Date": "12/09/2025", "Ref / Cheque No": "DLXBH25252000150",  # SAMPLE date + UTR
     "Credit": "0.00", "Debit": "1,96,000.00", "Balance": "xxxxxxx"},
    {"Txn Date": "15/09/2025", "Description": "NEFT DR-DLXBH25252000188-ABC PHARMA DISTRIBUTORS",
     "Value Date": "15/09/2025", "Ref / Cheque No": "DLXBH25252000188",
     "Credit": "0.00", "Debit": "5,25,060.00", "Balance": "xxxxxxx"},
]

GDN_SOURCE = [  # only INV-2291 has a goods-return deduction
    {"Date": "2025-09-10 00:00:00", "Particulars": "ABC Pharma Distributors",  # SAMPLE date
     "Voucher Type": "Debit Note", "Voucher No.": "457", "Voucher Ref. No.": "INV-2291",
     "Narration": "Goods returned (DN-0457)", "Gross Total": "20000"},
]

TDS_SOURCE = [  # only INV-2310 had TDS cut
    {"PARTY NAME": "ABC PHARMA DISTRIBUTORS", "Inv No": "INV-2310",
     "Inv Date": "2025-09-05 00:00:00",  # SAMPLE
     "INVOICE Taxable VALUE": "200000", "TDS": "4000", "Total TDS": "4000"},
]

VENDORS_SOURCE = [  # the real list repeats names; the duplicate must be deduped
    {"S.No": "1", "Vendor\nName": "ABC Pharma Distributors", "Email ID": "accounts@abcpharma.example"},
    {"S.No": "2", "Vendor\nName": "ABC Pharma Distributors", "Email ID": "accounts@abcpharma.example"},
]

# ---- parsed rows (what ingest should store) ----

CONSOLIDATED_ENTRIES = [
    {"vendor_name": "ABC PHARMA DISTRIBUTORS", "utr": "DLXBH25252000123", "invoice_no": "INV-2305",
     "po_no": "SE/PH/2025-26/0901", "grn_no": "SE/PH/GRN/25/3101",
     "invoice_amount": Decimal("120000.00"), "cheque_amount": Decimal("120000.00"),
     "debit_note": Decimal("0.00"), "diff": Decimal("0.00"), "transaction_date": date(2025, 9, 12)},
    {"vendor_name": "ABC PHARMA DISTRIBUTORS", "utr": "DLXBH25252000150", "invoice_no": "INV-2310",
     "po_no": "SE/PH/2025-26/0907", "grn_no": "SE/PH/GRN/25/3110",
     "invoice_amount": Decimal("200000.00"), "cheque_amount": Decimal("196000.00"),
     "debit_note": Decimal("4000.00"), "diff": Decimal("4000.00"), "transaction_date": date(2025, 9, 12)},
    {"vendor_name": "ABC PHARMA DISTRIBUTORS", "utr": "DLXBH25252000188", "invoice_no": "INV-2291",
     "po_no": "SE/PH/2025-26/0876", "grn_no": "SE/PH/GRN/25/3050",
     "invoice_amount": Decimal("545060.00"), "cheque_amount": Decimal("525060.00"),
     "debit_note": Decimal("20000.00"), "diff": Decimal("20000.00"), "transaction_date": date(2025, 9, 15)},
]

BANK_TRANSACTIONS = {  # by UTR
    "DLXBH25252000123": {"value_date": date(2025, 9, 12), "utr": "DLXBH25252000123", "debit": Decimal("120000.00"),
                         "description": BANK_SOURCE[0]["Description"], "vendor_name": "ABC PHARMA DISTRIBUTORS"},
    "DLXBH25252000150": {"value_date": date(2025, 9, 12), "utr": "DLXBH25252000150", "debit": Decimal("196000.00"),
                         "description": BANK_SOURCE[1]["Description"], "vendor_name": "ABC PHARMA DISTRIBUTORS"},
    "DLXBH25252000188": {"value_date": date(2025, 9, 15), "utr": "DLXBH25252000188", "debit": Decimal("525060.00"),
                         "description": BANK_SOURCE[2]["Description"], "vendor_name": "ABC PHARMA DISTRIBUTORS"},
}

# ---- expected reconciliation_results, by invoice_no ----

EXPECTED_RESULTS = {
    "INV-2305": {"invoice_value": Decimal("120000.00"), "payment_date": date(2025, 9, 12),
                 "amount_paid": Decimal("120000.00"), "tds_amount": None, "invoice_deduction": None,
                 "reason": None, "status": "PAID_IN_FULL", "exception_type": None},
    "INV-2310": {"invoice_value": Decimal("200000.00"), "payment_date": date(2025, 9, 12),
                 "amount_paid": Decimal("196000.00"), "tds_amount": Decimal("4000.00"), "invoice_deduction": None,
                 "reason": None, "status": "TDS_ONLY", "exception_type": None},
    "INV-2291": {"invoice_value": Decimal("545060.00"), "payment_date": date(2025, 9, 15),
                 "amount_paid": Decimal("525060.00"), "tds_amount": None, "invoice_deduction": Decimal("20000.00"),
                 "reason": "Goods returned (DN-0457)", "status": "DEDUCTION", "exception_type": None},
}

# ---- expected email table, cell by cell; empty cells are "" ----

EMAIL_HEADER = ["Invoice No", "Invoice Amount", "UTR", "Payment Date", "Amount Paid",
                "TDS Amount", "Invoice Deduction", "Reason"]

EMAIL_ROWS = {
    "INV-2305": ["INV-2305", "1,20,000.00", "DLXBH25252000123", "12-Sep-25", "1,20,000.00", "", "", ""],
    "INV-2310": ["INV-2310", "2,00,000.00", "DLXBH25252000150", "12-Sep-25", "1,96,000.00", "4,000.00", "", ""],
    "INV-2291": ["INV-2291", "5,45,060.00", "DLXBH25252000188", "15-Sep-25", "5,25,060.00", "", "20,000.00",
                 "Goods returned (DN-0457)"],
}

# Same vendor, same payment date -> one email. Keyed by payment date.
EMAIL_GROUPS = {
    date(2025, 9, 12): ["INV-2305", "INV-2310"],
    date(2025, 9, 15): ["INV-2291"],
}

# T+2 business days, Sundays skipped: payment date -> email_queue.send_on_date
SEND_ON_DATES = {
    date(2025, 9, 12): date(2025, 9, 15),  # Fri -> Mon
    date(2025, 9, 15): date(2025, 9, 17),  # Mon -> Wed
}
