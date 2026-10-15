"""Pydantic schemas + semantic validation for the LLM layer.

Two layers:
  1. Structural: pydantic models (``Profile``, ``Answer``, ...) - guarantees the
     JSON shape parses.
  2. Semantic: ``coerce_fields`` validates every field *value* against the controlled
     vocabularies in CONTRACT.md. Invalid values are never allowed to survive as a
     guess - they are nulled and flagged for a follow-up question.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Controlled vocabularies (see CONTRACT.md; all marked [ASSUMPTION])
# --------------------------------------------------------------------------- #

LOCATION_TYPES = ("urban_flagship", "suburban_medium", "rural_kiosk")  # aligned to Member 1
INCOME_BANDS = ("low", "medium", "high")
SHOP_CATEGORIES = (
    "grocery", "pharmacy", "clothing", "electronics", "hardware", "restaurant",
    "cosmetics", "stationery", "general_store", "bakery", "mobile_accessories",
)
NEARBY_ANCHORS = (
    "school", "university", "market", "mosque", "church", "temple", "hospital",
    "clinic", "mall", "bus_station", "railway_station", "factory", "office",
    "residential_area", "park", "stadium",
)
LANGUAGES = ("en", "ur", "es", "sw", "hi", "ar")

EXTRACTION_FIELDS = (
    "location_type", "income_band", "payday", "nearby_anchors",
    "shop_category", "currency", "budget", "language_detected",
)

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


# --------------------------------------------------------------------------- #
# Core models
# --------------------------------------------------------------------------- #

class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class FollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    question: str
    reason: Literal["low_confidence", "missing"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    follow_up_questions: list[FollowUp] = Field(default_factory=list)
    needs_confirmation: bool = False
    locale: str | None = None
    source_language: str | None = None
    text: str = ""
    audit_id: str = ""
    model: str = ""
    created_at: str = ""

    def field(self, name: str) -> FieldValue:
        return self.fields.get(name, FieldValue(value=None, confidence=0.0))

    def value(self, name: str) -> Any:
        return self.field(name).value

    def to_plain(self) -> dict:
        """Language-neutral JSON dict (contract shape)."""
        return {
            "fields": {k: {"value": v.value, "confidence": v.confidence}
                       for k, v in self.fields.items()},
            "follow_up_questions": [q.model_dump() for q in self.follow_up_questions],
            "needs_confirmation": self.needs_confirmation,
            "locale": self.locale,
            "source_language": self.source_language,
            "text": self.text,
            "audit_id": self.audit_id,
            "model": self.model,
            "created_at": self.created_at,
        }


class FigureRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: float
    source_path: str
    label: str | None = None
    display: str | None = None


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    language: str
    figures_cited: list[FigureRef] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    guard_passed: bool = True
    refused: bool = False
    question_type: str = "general"
    audit_id: str = ""


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float
    currency: str | None = None
    raw: str = ""
    locale: str | None = None


class DateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    iso: str
    kind: Literal["explicit_day", "end_of_month", "next_month_start", "relative", "parsed"]
    raw: str = ""
    locale: str | None = None


class PlaceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched: bool
    matched_name: str | None = None
    location_type: str | None = None
    confidence: float = 0.0
    region: str | None = None
    kind: str | None = None


# --------------------------------------------------------------------------- #
# Semantic validation / coercion
# --------------------------------------------------------------------------- #

class FieldIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    reason: Literal["missing", "invalid"]
    raw: Any = None


def _coerce_enum(value: Any, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    s = s.replace("-", "_").replace(" ", "_")
    return s if s in allowed else None


def _coerce_payday(value: Any) -> list[int | str] | None:
    """Normalize to a sorted list of ints 1..31 and/or the token 'last'."""
    if value is None:
        return None
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[int | str] = []
    for it in items:
        if isinstance(it, str) and it.strip().lower() in {"last", "last_day", "end"}:
            out.append("last")
            continue
        try:
            n = int(float(it))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 31:
            out.append(n)
    if not out:
        return None
    # dedupe, keep ints sorted, 'last' at the end
    ints = sorted({x for x in out if isinstance(x, int)})
    return ints + (["last"] if "last" in out else [])


def _coerce_anchor_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[str] = []
    for it in items:
        s = _coerce_enum(it, NEARBY_ANCHORS)
        if s and s not in out:
            out.append(s)
    return out or None


def _coerce_currency(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper()
    return s if _CURRENCY_RE.match(s) else None


def _coerce_budget(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def coerce_field(name: str, value: Any) -> tuple[Any, bool]:
    """Return (coerced_value, ok). ok=False means the raw value was invalid/missing."""
    if name == "location_type":
        c = _coerce_enum(value, LOCATION_TYPES)
    elif name == "income_band":
        c = _coerce_enum(value, INCOME_BANDS)
    elif name == "shop_category":
        c = _coerce_enum(value, SHOP_CATEGORIES)
    elif name == "language_detected":
        c = _coerce_enum(value, LANGUAGES)
    elif name == "nearby_anchors":
        c = _coerce_anchor_list(value)
    elif name == "payday":
        c = _coerce_payday(value)
    elif name == "currency":
        c = _coerce_currency(value)
    elif name == "budget":
        c = _coerce_budget(value)
    else:
        return value, value is not None
    return c, c is not None


def coerce_fields(raw_fields: dict[str, Any]) -> tuple[dict[str, FieldValue], list[FieldIssue]]:
    """Convert a raw ``{field: value}`` or ``{field: {value, confidence}}`` map into
    validated ``FieldValue`` objects. Never raises; invalid values are nulled and
    reported so the caller can raise a follow-up question.
    """
    fields: dict[str, FieldValue] = {}
    issues: list[FieldIssue] = []
    for name in EXTRACTION_FIELDS:
        entry = raw_fields.get(name)
        conf = 0.0
        raw_val = None
        if isinstance(entry, dict) and "value" in entry:
            raw_val = entry.get("value")
            try:
                conf = float(entry.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
        else:
            raw_val = entry
            conf = 1.0 if entry is not None else 0.0
        coerced, ok = coerce_field(name, raw_val)
        if not ok:
            reason = "missing" if raw_val is None else "invalid"
            issues.append(FieldIssue(field=name, reason=reason, raw=raw_val))
            fields[name] = FieldValue(value=None, confidence=0.0)
        else:
            conf = max(0.0, min(1.0, conf if conf > 0 else 0.5))
            fields[name] = FieldValue(value=coerced, confidence=conf)
    return fields, issues
