"""Local geography: a small regional gazetteer.

Maps neighborhoods / markets / landmarks to Member 1's ``location_type`` enum.
Unknown places return ``matched=False`` so the caller raises a follow-up question
instead of guessing (CONTRACT.md §2.3, D. Local geography).
"""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .schemas import PlaceMatch

_DATA = Path(__file__).resolve().parent / "data" / "gazetteer_karachi.json"
_DEFAULT_REGION = "south_asia_karachi"
_FUZZY_THRESHOLD = 0.82  # [ASSUMPTION] min similarity to accept a fuzzy place match


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).lower()
    s = re.sub(r"[^a-z0-9\u0600-\u06ff\u0900-\u097f ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _load(region: str) -> dict:
    if region != _DEFAULT_REGION:
        raise KeyError(f"Unknown region '{region}'. Available: {_DEFAULT_REGION}")
    return json.loads(_DATA.read_text(encoding="utf-8"))


def available_regions() -> list[str]:
    return [_DEFAULT_REGION]


def region_currency(region: str = _DEFAULT_REGION) -> str:
    return _load(region).get("currency", "PKR")


def resolve_place(name: str, region: str = _DEFAULT_REGION) -> PlaceMatch:
    """Resolve a place mention to a location type + anchor. Never guesses."""
    if not name or not name.strip():
        return PlaceMatch(matched=False, region=region)
    data = _load(region)
    q = _norm(name)
    best: tuple[float, dict] | None = None

    for entry in data["entries"]:
        candidates = [entry["name"], *entry.get("aliases", [])]
        for cand in candidates:
            c = _norm(cand)
            if not c:
                continue
            if q == c:
                return _match(entry, region, 0.95)
            if re.search(rf"(?<!\w){re.escape(c)}(?!\w)", q):
                score = 0.85
            else:
                score = SequenceMatcher(None, q, c).ratio()
            if best is None or score > best[0]:
                best = (score, entry)

    if best and best[0] >= _FUZZY_THRESHOLD:
        return _match(best[1], region, round(min(best[0], 0.8), 2))
    return PlaceMatch(matched=False, region=region, confidence=0.0)


def _match(entry: dict, region: str, confidence: float) -> PlaceMatch:
    return PlaceMatch(
        matched=True,
        matched_name=entry["name"],
        location_type=entry.get("location_type"),
        confidence=confidence,
        region=region,
        kind=entry.get("kind"),
    )
