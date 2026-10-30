"""T+2 sending. Owner: Person A."""
from datetime import date, timedelta


def send_on_date(payment_date: date) -> date:
    """T+2 business days. Every day except Sunday is a business day; holidays are not skipped."""
    d, left = payment_date, 2
    while left:
        d += timedelta(days=1)
        if d.weekday() != 6:  # Sunday
            left -= 1
    return d
