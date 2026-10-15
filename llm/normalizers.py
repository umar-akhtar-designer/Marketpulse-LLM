"""Normalizers for informal money / quantities / dates, per locale.

Hand-rolled (no external locale data) so behaviour is deterministic and testable.
Every parse is meant to be shown back to the retailer for confirmation.

[ASSUMPTION] Locale separator conventions:
  * ``es`` (and generic EU) : thousands '.', decimal ','
  * everything else          : thousands ',', decimal '.'
When a string is genuinely ambiguous ("5.000", "5,00") the locale default is used and
the value is shown back for confirmation - never silently trusted.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .schemas import DateResult, Money

# --------------------------------------------------------------------------- #
# Digit + separator handling
# --------------------------------------------------------------------------- #

_DIGIT_MAP = {}
for _i, _base in enumerate((0x0660, 0x06F0, 0x0966)):  # Arabic-Indic, Extended, Devanagari
    for _d in range(10):
        _DIGIT_MAP[chr(_base + _d)] = str(_d)

_EU_LOCALES = ("es",)
_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "million": 1e6,
    "b": 1e9, "billion": 1e9,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "crore": 1e7, "crores": 1e7,
}


def _to_ascii_digits(text: str) -> str:
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in text)


def _locale_group(locale: str | None) -> str:
    if not locale:
        return "en"
    return locale.split("-")[0].lower()


def _parse_number(s: str, locale: str | None) -> float | None:
    s = s.strip()
    if not s:
        return None
    eu = _locale_group(locale) in _EU_LOCALES
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3 and not eu:
            s = s.replace(",", "")            # 5,000 -> 5000
        elif all(len(p) == 3 for p in parts[1:]) and not eu:
            s = s.replace(",", "")            # 1,000,000
        else:
            s = s.replace(",", ".")           # 5,00 -> 5.00
    elif has_dot:
        parts = s.split(".")
        if eu and len(parts) == 2 and len(parts[1]) == 3:
            s = s.replace(".", "")            # es: 5.000 -> 5000
        elif len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            s = s.replace(".", "")            # 1.000.000
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #

_CURRENCY_TOKENS = {
    "PKR": ("rs", "rs.", "pkr", "rupee", "rupees", "₨", "روپے", "روپیہ"),
    "INR": ("inr", "₹", "रुपये", "रुपया", "rupee", "rupees"),
    "USD": ("$", "usd", "dollar", "dollars"),
    "EUR": ("€", "eur", "euro", "euros", "euros"),
    "KES": ("kes", "ksh", "shilling", "shillings", "bob"),
    "SAR": ("sar", "riyal", "riyals", "﷼", "ريال"),
    "AED": ("aed", "dirham", "dirhams", "درهم"),
    "GBP": ("£", "gbp", "pound", "pounds"),
}
_NUM_WITH_MULT = re.compile(r"(\d[\d.,]*)\s*(k|m|b|lakhs?|lacs?|crores?|thousand|million|billion)?\b")


def normalize_money(text: str, locale: str | None = None) -> Money | None:
    """Parse an informal money string. Returns ``None`` if no amount is found."""
    if not text:
        return None
    raw = text
    s = _to_ascii_digits(text).lower()
    currency = None
    for code, tokens in _CURRENCY_TOKENS.items():
        if any(tok in s for tok in tokens):
            currency = code
            break
    m = _NUM_WITH_MULT.search(s)
    if not m:
        return None
    amount = _parse_number(m.group(1), locale)
    if amount is None:
        return None
    mult = m.group(2)
    if mult:
        amount *= _MULTIPLIERS.get(mult, 1.0)
    return Money(amount=float(amount), currency=currency, raw=raw, locale=locale)


# --------------------------------------------------------------------------- #
# Quantity
# --------------------------------------------------------------------------- #

def normalize_quantity(text: str, locale: str | None = None) -> float | None:
    """Parse an informal quantity: '3 dozen', 'half dozen', '1.5k' -> number."""
    if not text:
        return None
    s = _to_ascii_digits(text).lower()
    m = _NUM_WITH_MULT.search(s)
    if "dozen" in s:
        if m:
            base = _parse_number(m.group(1), locale)
            if base is None:
                base = 1.0
        else:
            base = 0.5 if "half" in s else 1.0
        if "half" in s and (not m or base == 1.0):
            return 6.0
        return float(base * 12.0)
    if not m:
        return None
    qty = _parse_number(m.group(1), locale)
    if qty is None:
        return None
    mult = m.group(2)
    if mult:
        qty *= _MULTIPLIERS.get(mult, 1.0)
    return float(qty)


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

_END_OF_MONTH = (
    "end of the month", "end of month", "eom", "end of this month",
    "fin de mes", "final del mes", "mahine ke aakhir", "mahine ke akhir",
    "mahine ke ant", "mwisho wa mwezi", "نهاية الشهر", "آخر الشهر", "مہینے کے آخر",
)
_START_NEXT_MONTH = (
    "start of next month", "beginning of next month", "next month start",
    "comienzo del proximo mes", "agla mahina shuru", "mwanzoni mwa mwezi ujao",
    "بداية الشهر القادم", "اگلے مہینے کی شروعات",
)
_RELATIVE = {
    "today": 0, "tomorrow": 1, "day after tomorrow": 2,
    "hoy": 0, "manana": 1, "mañana": 0, "pasado manana": 2,
    "aaj": 0, "kal": 1, "parson": 2,
    "leo": 0, "kesho": 1, "kesho kutwa": 2,
    "اليوم": 0, "غدا": 1, "غدًا": 1, "بعد غد": 2,
    "آج": 0, "کل": 1, "پرسوں": 2,
}
_DAY_RE = re.compile(r"\b(\d{1,2})\s*(?:st|nd|rd|th|tareekh|tarekh|tarikh|de|del)?\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _last_day_of_month(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def normalize_date(text: str, locale: str | None = None, today: date | None = None) -> DateResult | None:
    """Resolve informal dates ('end of the month', 'the 25th') using the locale."""
    if not text:
        return None
    today = today or date.today()
    raw = text
    s = _to_ascii_digits(text).lower().strip()

    iso = _ISO_RE.search(s)
    if iso:
        try:
            return DateResult(iso=f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}",
                              kind="parsed", raw=raw, locale=locale)
        except ValueError:
            pass

    if any(k in s for k in _END_OF_MONTH):
        return DateResult(iso=_last_day_of_month(today).isoformat(),
                          kind="end_of_month", raw=raw, locale=locale)

    if any(k in s for k in _START_NEXT_MONTH):
        first = date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
        return DateResult(iso=first.isoformat(), kind="next_month_start", raw=raw, locale=locale)

    for kw, days in _RELATIVE.items():
        if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", s):
            return DateResult(iso=(today + timedelta(days=days)).isoformat(),
                              kind="relative", raw=raw, locale=locale)

    day = _DAY_RE.search(s)
    if day:
        n = int(day.group(1))
        if 1 <= n <= 31:
            year, month = today.year, today.month
            try:
                candidate = date(year, month, n)
                if candidate < today:
                    month += 1
                    if month > 12:
                        month, year = 1, year + 1
                    candidate = date(year, month, n)
                return DateResult(iso=candidate.isoformat(), kind="explicit_day", raw=raw, locale=locale)
            except ValueError:
                return None
    return None
