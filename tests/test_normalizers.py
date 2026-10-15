"""Normalizer unit tests: informal money / quantity / date strings per locale."""

from datetime import date

import pytest

from llm.normalizers import normalize_date, normalize_money, normalize_quantity

TODAY = date(2026, 10, 15)

MONEY_CASES = [
    ("30k", "en-PK", 30000.0, None),  # no currency token; region default applied later
    ("5,000", "en", 5000.0, None),
    ("5,000.50", "en", 5000.50, None),
    ("5.000,00", "es", 5000.0, None),
    ("Rs 30,000", "en-PK", 30000.0, "PKR"),
    ("30,000 rupees", "en-PK", 30000.0, "PKR"),
    ("2 lakh", "en-PK", 200000.0, None),
    ("1.5 crore", "en-IN", 15000000.0, None),
    ("₨5000", "en-PK", 5000.0, "PKR"),
    ("€1.200,50", "es", 1200.50, "EUR"),
    ("बजट 5000 रुपये", "hi", 5000.0, "INR"),
]

DATE_CASES = [
    ("the 25th", "en-PK", TODAY, "2026-10-25", "explicit_day"),
    ("the 25th", "en-PK", date(2026, 10, 30), "2026-11-25", "explicit_day"),
    ("end of the month", "en", TODAY, "2026-10-31", "end_of_month"),
    ("fin de mes", "es", date(2026, 2, 10), "2026-02-28", "end_of_month"),
    ("tomorrow", "en", TODAY, "2026-10-16", "relative"),
    ("2026-11-01", "en", TODAY, "2026-11-01", "parsed"),
    ("25 tareekh", "en-PK", TODAY, "2026-10-25", "explicit_day"),
    ("مہینے کے آخر", "ur", TODAY, "2026-10-31", "end_of_month"),
]

QUANTITY_CASES = [
    ("3 dozen", "en", 36.0),
    ("half dozen", "en", 6.0),
    ("1.5k", "en", 1500.0),
    ("12", "en", 12.0),
]


@pytest.mark.parametrize("text,locale,amount,currency", MONEY_CASES)
def test_money(text, locale, amount, currency):
    m = normalize_money(text, locale)
    assert m is not None, f"failed to parse {text!r}"
    assert m.amount == pytest.approx(amount)
    if currency is not None:
        assert m.currency == currency


@pytest.mark.parametrize("text,locale,today,iso,kind", DATE_CASES)
def test_date(text, locale, today, iso, kind):
    d = normalize_date(text, locale, today=today)
    assert d is not None, f"failed to parse {text!r}"
    assert d.iso == iso
    assert d.kind == kind


@pytest.mark.parametrize("text,locale,expected", QUANTITY_CASES)
def test_quantity(text, locale, expected):
    q = normalize_quantity(text, locale)
    assert q == pytest.approx(expected)


def test_money_none_when_no_number():
    assert normalize_money("no amount here", "en") is None


def test_date_none_when_unparsable():
    assert normalize_date("sometime soon-ish", "en", today=TODAY) is None
