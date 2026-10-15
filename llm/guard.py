"""Number guard: every figure in an explanation must trace to source data.

[ASSUMPTION] Grounding rule: a number cited in the answer is "grounded" if it matches
(within tolerance) any numeric value found anywhere in the optimizer output, the
``explain_inputs()`` facts, or the forecasts - including numbers embedded in reason
strings. Tolerance: exact after rounding to 2 dp, or |diff| <= 0.01.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .schemas import FigureRef

_DIGIT_MAP = {}
for _base in (0x0660, 0x06F0, 0x0966):
    for _d in range(10):
        _DIGIT_MAP[chr(_base + _d)] = str(_d)

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*%?")


def to_ascii_digits(text: str) -> str:
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in text)


def _parse_token(tok: str) -> float | None:
    s = tok.strip().rstrip(".,").rstrip("%").replace(" ", "")
    s = s.replace(",", "")
    # if multiple dots remain, keep the last as decimal
    if s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _numbers_in_obj(obj: Any, path: str, out: dict[str, str]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out[str(float(obj))] = path
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _numbers_in_obj(v, f"{path}.{k}" if path else str(k), out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _numbers_in_obj(v, f"{path}[{i}]", out)
    elif isinstance(obj, str):
        for tok in _NUM_RE.findall(to_ascii_digits(obj)):
            val = _parse_token(tok)
            if val is not None:
                out.setdefault(str(val), path)


def build_grounded(sources: dict[str, Any]) -> dict[str, str]:
    """Flatten all numeric values (leaf values + numbers inside strings) -> path."""
    out: dict[str, str] = {}
    for name, obj in sources.items():
        _numbers_in_obj(obj, name, out)
    # also index canonical string forms so "48" matches 48.0 etc.
    extra: dict[str, str] = {}
    for k, path in out.items():
        try:
            v = float(k)
        except ValueError:
            continue
        for form in (f"{v:.2f}", f"{v:g}"):
            extra.setdefault(form, path)
        if abs(v - round(v)) < 1e-9:
            extra.setdefault(str(int(round(v))), path)
    out.update(extra)
    return out


def _matches(value: float, grounded: dict[str, str]) -> tuple[bool, str | None]:
    for form in (str(value), f"{value:g}", f"{value:.2f}"):
        if form in grounded:
            return True, grounded[form]
    for k, path in grounded.items():
        try:
            gv = float(k)
        except ValueError:
            continue
        if abs(gv - value) <= 0.01:
            return True, path
    return False, None


@dataclass
class GuardResult:
    ok: bool
    ungrounded: list[str] = field(default_factory=list)
    figures: list[FigureRef] = field(default_factory=list)


def check_numbers(text: str, sources: dict[str, Any]) -> GuardResult:
    grounded = build_grounded(sources)
    figures: list[FigureRef] = []
    ungrounded: list[str] = []
    seen: set[str] = set()
    for tok in _NUM_RE.findall(to_ascii_digits(text)):
        val = _parse_token(tok)
        if val is None:
            continue
        ok, path = _matches(val, grounded)
        if not ok and tok.strip().endswith("%"):   # "12%" is grounded by 0.12
            ok, path = _matches(val / 100.0, grounded)
        if ok:
            if tok not in seen:
                figures.append(FigureRef(value=val, source_path=path or "", display=tok))
                seen.add(tok)
        else:
            ungrounded.append(tok)
    return GuardResult(ok=not ungrounded, ungrounded=ungrounded, figures=figures)
