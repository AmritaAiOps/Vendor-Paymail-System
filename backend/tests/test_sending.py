from datetime import date

from app.sending import send_on_date


def test_t_plus_2_skips_sundays_only():
    assert send_on_date(date(2025, 9, 11)) == date(2025, 9, 13)  # Thu -> Sat
    assert send_on_date(date(2025, 9, 12)) == date(2025, 9, 15)  # Fri -> Mon (Sunday skipped)
    assert send_on_date(date(2025, 9, 13)) == date(2025, 9, 16)  # Sat -> Tue
    assert send_on_date(date(2025, 9, 15)) == date(2025, 9, 17)  # Mon -> Wed
