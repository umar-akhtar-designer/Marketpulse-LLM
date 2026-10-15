"""Generate a reproducible multilingual extraction eval set (~100 items).

Design:
  * A small set of "specs" (place, shop category, budget, payday, anchor).
  * Each spec is rendered into every supported language (incl. code-switched),
    producing a free-form shop description + the gold label for the fields the
    sentence intentionally states.

The generator is DETERMINISTIC (no RNG): run it and commit the output so the
harness and CI score the exact same items.

    python eval/build_eval.py            # writes eval/descriptions.jsonl

Gold is only defined for fields the sentence states, so unstated fields are not
penalised (the extractor is expected to raise a follow-up instead of guessing).
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "descriptions.jsonl"

# (place name, expected location_type from the gazetteer)
PLACES = [
    ("Clifton", "urban_flagship"),
    ("Empress Market", "urban_flagship"),
    ("Liaquatabad", "suburban_medium"),
    ("North Nazimabad", "suburban_medium"),
    ("Gadap Town", "rural_kiosk"),
    ("Surjani Town", "rural_kiosk"),
]
CATEGORIES = ["grocery", "pharmacy", "clothing", "restaurant", "bakery"]
BUDGETS = [3000, 5000, 8000, 12000, 25000, 30000]
PAYDAYS = [1, 10, 15, 25, 28, 30]

# The category word actually used in each language (must be recognised by the
# extractor's keyword tables).
CAT_WORD = {
    "en": {"grocery": "grocery", "pharmacy": "pharmacy", "clothing": "clothing",
           "restaurant": "restaurant", "bakery": "bakery"},
    "ur": {"grocery": "kirana", "pharmacy": "dawa", "clothing": "kapray",
           "restaurant": "dhaba", "bakery": "bakery"},
    "es": {"grocery": "abarrotes", "pharmacy": "farmacia", "clothing": "ropa",
           "restaurant": "restaurante", "bakery": "panaderia"},
    "sw": {"grocery": "duka la vyakula", "pharmacy": "duka la dawa", "clothing": "nguo",
           "restaurant": "mkahawa", "bakery": "mkate"},
    "hi": {"grocery": "किराना", "pharmacy": "दवा", "clothing": "कपड़े",
           "restaurant": "भोजनालय", "bakery": "बेकरी"},
    "ar": {"grocery": "بقالة", "pharmacy": "صيدلية", "clothing": "ملابس",
           "restaurant": "مطعم", "bakery": "مخبز"},
}

# currency word used per language + the ISO code it should normalise to.
CCY = {
    "en": ("rupees", "PKR"), "ur": ("rupees", "PKR"), "es": ("euros", "EUR"),
    "sw": ("shillings", "KES"), "hi": ("रुपये", "INR"), "ar": ("ريال", "SAR"),
}

LANGS = ["en", "ur", "es", "sw", "hi", "ar"]


def render(lang: str, place: str, cat: str, budget: int, payday: int) -> str:
    word = CAT_WORD[lang][cat]
    ccy = CCY[lang][0]
    if lang == "en":
        return (f"I run a {word} shop in {place} near a school, "
                f"budget {budget} {ccy}, payday {payday}")
    if lang == "ur":
        return (f"{place} ke paas meri {word} dukan hai, school ke qareeb, "
                f"budget {budget} {ccy}, payday {payday}")
    if lang == "es":
        return (f"mi tienda de {word} en {place}, cerca de una escuela, "
                f"presupuesto {budget} {ccy}, pago el {payday}")
    if lang == "sw":
        return (f"duka langu la {word} {place}, karibu na shule, "
                f"bajeti {budget} {ccy}, mshahara {payday}")
    if lang == "hi":
        return (f"{place} के पास मेरी {word} दुकान है, स्कूल के क़रीब, "
                f"बजट {budget} {ccy}, वेतन {payday}")
    if lang == "ar":
        return (f"متجري {word} في {place}, قرب مدرسة, "
                f"ميزانية {budget} {ccy}, راتب {payday}")
    raise ValueError(lang)


def render_code_switched(place: str, cat: str, budget: int, payday: int) -> str:
    # Roman-Urdu + English mix, very common in Karachi shop scripts / chat.
    word = CAT_WORD["en"][cat]
    return (f"{place} ke paas my {word} shop hai, budget {budget} rupees, "
            f"payday {payday}, near a school")


def specs():
    for i in range(14):  # 14 specs x 7 renderings = 98 items: cycle to mix combinations
        place, loc = PLACES[i % len(PLACES)]
        cat = CATEGORIES[i % len(CATEGORIES)]
        budget = BUDGETS[i % len(BUDGETS)]
        payday = PAYDAYS[i % len(PAYDAYS)]
        yield f"spec{i:02d}", place, loc, cat, budget, payday


def main() -> None:
    rows = []
    for spec_id, place, loc, cat, budget, payday in specs():
        gold = {
            "shop_category": cat,
            "budget": float(budget),
            "currency": None,          # filled per language below
            "payday": [payday],
            "location_type": loc,
            "nearby_anchors": ["school"],
        }
        for lang in LANGS:
            g = dict(gold, currency=CCY[lang][1])
            rows.append({
                "id": f"{spec_id}-{lang}",
                "spec_id": spec_id,
                "lang": lang,
                "text": render(lang, place, cat, budget, payday),
                "gold": g,
            })
        # code-switched variant
        rows.append({
            "id": f"{spec_id}-cs",
            "spec_id": spec_id,
            "lang": "cs",
            "text": render_code_switched(place, cat, budget, payday),
            "gold": dict(gold, currency="PKR"),
        })

    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                   encoding="utf-8")
    print(f"wrote {len(rows)} items -> {OUT}")


if __name__ == "__main__":
    main()
