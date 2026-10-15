"""MarketPulse AI - Member 4 (LLM Layer).

Public surface:
    extract_profile(text) -> Profile
    apply_corrections(profile, edits) -> Profile
    explain(question, plan, forecasts, lang) -> Answer
    resolve_place(name) -> PlaceMatch

See CONTRACT.md for the exact schemas and labeled assumptions.
"""

from .schemas import (
    Profile,
    FieldValue,
    FollowUp,
    Answer,
    FigureRef,
    Money,
    DateResult,
    PlaceMatch,
    EXTRACTION_FIELDS,
    LOCATION_TYPES,
    INCOME_BANDS,
    SHOP_CATEGORIES,
    NEARBY_ANCHORS,
    LANGUAGES,
)
from .extraction import extract_profile, apply_corrections
from .explainer import explain
from .gazetteer import resolve_place

__all__ = [
    "Profile",
    "FieldValue",
    "FollowUp",
    "Answer",
    "FigureRef",
    "Money",
    "DateResult",
    "PlaceMatch",
    "EXTRACTION_FIELDS",
    "LOCATION_TYPES",
    "INCOME_BANDS",
    "SHOP_CATEGORIES",
    "NEARBY_ANCHORS",
    "LANGUAGES",
    "extract_profile",
    "apply_corrections",
    "explain",
    "resolve_place",
]
