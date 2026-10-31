"""Where each field lives in each input file: the one place to edit when a header changes.
Headers match ignoring case, spaces and punctuation, so "UTR NO:", "UTR No" and "utr no" are the same.
The first alias is the name used in error messages. Aliases are tried in order; the first match wins."""

COLUMNS = {
    "consolidated": {
        "vendor_name": ["benefName", "Vendor Name"],
        "utr": ["UTR NO:"],
        "invoice_no": ["Narration 2- Invoice No", "Invoice No"],
        "po_no": ["Narration 3- PO No", "PO No"],
        "grn_no": ["GRN NO:"],
        "invoice_amount": ["Invoice Amount"],
        "cheque_amount": ["Cheque Amount"],
        "debit_note": ["Debit Note"],
        "diff": ["Diff"],
        "transaction_date": ["Transaction Date"],
    },
    "bank": {
        "value_date": ["Value Date"],
        "utr": ["Ref / Cheque No", "Ref No", "UTR"],
        "debit": ["Debit"],
        "description": ["Description"],
    },
    "gdn": {
        "gdn_date": ["Date"],
        "vendor_name": ["Particulars"],
        "voucher_no": ["Voucher No."],
        "invoice_no": ["Voucher Ref. No."],
        "amount": ["Gross Total"],
        "reason": ["Narration"],
    },
    "tds": {
        "vendor_name": ["PARTY NAME"],
        "invoice_no": ["Inv No"],
        "invoice_date": ["Inv Date"],
        "tds_amount": ["TDS", "Total TDS"],  # the real file has two "TDS " columns; the first holds the amount
    },
    "vendors": {
        "party_name": ["Vendor Name", "Party Name"],
        "email": ["Email ID", "Email id"],
        "email_2": ["Email ID- Contact 2"],  # optional: contact 2 is mailed too
    },
}

REQUIRED = {
    "consolidated": ["vendor_name", "utr", "invoice_no", "invoice_amount", "cheque_amount", "transaction_date"],
    "bank": ["value_date", "utr", "debit", "description"],
    "gdn": ["vendor_name", "invoice_no", "amount", "reason"],
    "tds": ["vendor_name", "invoice_no", "tds_amount"],
    "vendors": ["party_name", "email"],
}
