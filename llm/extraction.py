"""Extraction: free-form shop description -> language-neutral ``Profile``.

Two interchangeable back ends, same output contract:
  * ``_llm_extract``  - real LLM + JSON schema (used with the AMD endpoint).
  * ``_rule_extract`` - deterministic regex/keyword extractor (offline demo + tests).

Both feed through ``coerce_fields`` (semantic validation) and then a shared
post-processing step (normalizers + gazetteer + confidence/follow-up logic), so the
retailer always receives a schema-valid Profile and never a silent guess.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .audit import log_event, sha256
from .client import LLMClient, get_default_client
from .config import Settings, get_settings
from .gazetteer import region_currency, resolve_place
from .normalizers import normalize_date, normalize_money
from .schemas import (
    EXTRACTION_FIELDS,
    FieldValue,
    FollowUp,
    Profile,
    coerce_fields,
)

_PROMPT = (Path(__file__).resolve().parent / "prompts" / "extraction.txt").read_text(encoding="utf-8")

_FIELD_SPEC = """  location_type: one of urban_flagship | suburban_medium | rural_kiosk
  income_band: one of low | medium | high
  payday: list of day-of-month ints 1-31 and/or "last"
  nearby_anchors: list from [school, university, market, mosque, church, temple,
                  hospital, clinic, mall, bus_station, railway_station, factory,
                  office, residential_area, park, stadium]
  shop_category: one of [grocery, pharmacy, clothing, electronics, hardware,
                 restaurant, cosmetics, stationery, general_store, bakery,
                 mobile_accessories]
  currency: ISO-4217 e.g. PKR, USD, EUR
  budget: number
  language_detected: one of en | ur | es | sw | hi | ar"""

# --------------------------------------------------------------------------- #
# Keyword tables (all [ASSUMPTION]: hand-set, extendable per release)
# --------------------------------------------------------------------------- #

_SCRIPT = {"arabic": (0x0600, 0x06FF), "devanagari": (0x0900, 0x097F)}

_ROMAN_LANG_KW = {
    "ur": {"kyun", "kyu", "hai", "hain", "aur", "mera", "meri", "dukan", "dukaan",
           "rupees", "rupay", "tareekh", "tarekh", "mahine", "mahina", "paas", "ke",
           "ka", "ki", "bazaar", "masjid", "kirana", "payday", "tankha", "bajet", "ka",
           "sasta", "gareeb", "ameer", "shehar", "gaon", "ke qareeb", "qareeb"},
    "es": {"tengo", "tienda", "cerca", "de", "y", "presupuesto", "pago", "barrio",
           "mercado", "escuela", "cerca", "un", "el", "la", "los", "para", "con",
           "fin", "mes", "dia", "pesos", "colon", "abarrotes", "farmacia"},
    "sw": {"duka", "karibu", "na", "bajeti", "malipo", "mwezi", "soko", "shule",
           "hospitali", "na", "ya", "kwa", "bei", "pesa", "nanukuu"},
    "en": {"shop", "store", "near", "budget", "payday", "market", "road", "grocery",
           "income", "salary", "the", "and", "of", "with", "month", "end"},
}
_LANG_SCRIPT_KW = {
    "ar": {"ميزانية", "راتب", "شهر", "قريب", "بقالة", "سوق", "مدرسة", "دخل"},
    "ur": {"بجٹ", "تنخواہ", "مہینے", "قریب", "کریانہ", "بازار", "اسکول", "دکان", "آمدنی"},
    "hi": {"बजट", "वेतन", "महीने", "पास", "किराना", "बाजार", "स्कूल", "दुकान", "आय"},
}

_CATEGORY_KW = [
    ("pharmacy", ["pharmacy", "medical store", "chemist", "dawai", "dawa", "medicine",
                  "صیدلیہ", "فارمیسی", "farmacia", "duka la dawa", "صيدلية", "दवा"]),
    ("bakery", ["bakery", "baker", "bread", "cake", "naan", "بیکری", "panaderia",
                "बेकरी", "مخبز", "mkate"]),
    ("mobile_accessories", ["mobile accessories", "mobile shop", "phone shop", "sim card"]),
    ("electronics", ["electronics", "electronic", "appliance", "appliances", "tv shop"]),
    ("hardware", ["hardware", "paint shop", "building material", "cement", "tools"]),
    ("clothing", ["clothing", "clothes", "kapray", "kapre", "garment", "boutique",
                  "fashion", "ropa", "nguo", "ملابس", "कपड़े"]),
    ("restaurant", ["restaurant", "cafe", "dhaba", "eatery", "restaurante", "mkahawa",
                    "مطعم", "hotel food", "भोजनालय"]),
    ("cosmetics", ["cosmetics", "cosmetic", "beauty", "salon", "makeup"]),
    ("stationery", ["stationery", "stationary", "book shop", "books", "photocopy"]),
    ("grocery", ["grocery", "grocer", "kirana", "karyana", "rashan", "supermarket",
                 "super market", "سودا", "کریانہ", "بقالة", "abarrotes", "duka la vyakula",
                 "किराना"]),
    ("general_store", ["general store", "kiosk", "shop", "store", "dukan", "dukaan",
                       "toko", "tienda", "متجر", "دکان"]),
]

_ANCHOR_KW = [
    ("school", ["school", "madrasa", "madrasah", "اسکول", "مدرسه", "escuela", "shule",
                "مدرسة", "स्कूल"]),
    ("university", ["university", "college", "campus", "یونیورسٹی", "جامعہ",
                    "universidad", "chuo kikuu", "جامعة"]),
    ("market", ["market", "bazaar", "bazar", "mandi", "مارکیٹ", "بازار", "mercado", "soko", "سوق"]),
    ("mosque", ["mosque", "masjid", "jamia", "مسجد", "mezquita", "msikiti"]),
    ("church", ["church", "cathedral", "گرجا", "iglesia", "kanisa", "كنيسة"]),
    ("temple", ["temple", "mandir", "مندر", "templo", "hekalu", "معبد"]),
    ("hospital", ["hospital", "اسپتال", "ہسپتال", "hospitali", "مستشفى"]),
    ("clinic", ["clinic", "dispensary", "کلینک", "clinica", "kliniki", "عيادة"]),
    ("mall", ["mall", "shopping centre", "shopping center", "plaza", "مال",
              "centro comercial", "jumba la maduka", "مول"]),
    ("bus_station", ["bus stop", "bus station", "bus stand", "adda", "بس اسٹاپ",
                     "parada", "kituo cha basi", "موقف الباص"]),
    ("railway_station", ["railway station", "train station", "ریلوے اسٹیشن",
                         "estacion de tren", "kituo cha treni", "محطة القطار"]),
    ("factory", ["factory", "industrial", "mill", "plant", "فیکٹری", "fabrica", "kiwanda", "مصنع"]),
    ("office", ["office", "bank", "دفتر", "oficina", "ofisi", "مكتب"]),
    ("residential_area", ["residential", "colony", "neighbourhood", "neighborhood",
                          "society", "محلہ", "colonia", "mtaa", "حي"]),
    ("park", ["park", "garden", "bagh", "پارک", "parque", "bustani", "حديقة"]),
    ("stadium", ["stadium", "اسٹیڈیم", "estadio", "uwanja", "ملعب"]),
]

_LOC_TYPE_KW = [
    ("rural_kiosk", ["village", "gaon", "rural", "outskirts", "دیہات", "گاؤں",
                     "kijiji", "قرية", "gadap", "surjani", "baldia"]),
    ("suburban_medium", ["residential", "colony", "scheme", "society", "township",
                         "suburb", "محلہ", "colonia", "mtaa"]),
    ("urban_flagship", ["city center", "city centre", "downtown", "main bazaar",
                        "main market", "commercial", "شہر", "centro", "katikati", "وسط المدينة"]),
]

_INCOME_KW = [
    ("low", ["low income", "poor", "sasta", "gareeb", "ghareeb", "lower class",
             "غریب", "bajo", "منخفض", "कम आय"]),
    ("high", ["high income", "rich", "wealthy", "affluent", "ameer", "امیر",
              "upper class", "alto", "tajiri", "عالي", "उच्च आय"]),
    ("medium", ["middle class", "middle income", "average", "درمیانہ", "medio",
                "kati", "متوسط", "मध्यम आय"]),
]

_PAYDAY_KW = ["payday", "salary", "tankha", "تنخواہ", "sueldo", "pago", "pagos",
              "mshahara", "راتب", "वेतन", "pay day", "tankhwah"]

_FOLLOWUP_Q = {
    "location_type": {
        "en": "Is your shop in a busy city centre, a residential area, or a village/outskirts?",
        "ur": "آپ کی دکان شہر کے مرکز میں، رہائشی علاقے میں، یا گاؤں/باہر ہے؟",
        "es": "¿Su tienda está en el centro de la ciudad, en una zona residencial o en un pueblo?",
        "sw": "Duka lako liko katikati ya mji, mtaa wa makazi, au kijijini?",
        "hi": "आपकी दुकान शहर के केंद्र, आवासीय क्षेत्र, या गाँव में है?",
        "ar": "هل متجرك في وسط المدينة، أو منطقة سكنية، أو قرية؟",
    },
    "income_band": {
        "en": "Would you describe your neighborhood as low, middle, or high income?",
        "ur": "آپ کا محلہ کم، درمیانہ، یا زیادہ آمدنی والا ہے؟",
        "es": "¿Su barrio es de ingresos bajos, medios o altos?",
        "sw": "Mtaa wako una kipato cha chini, kati, au juu?",
        "hi": "आपका इलाका कम, मध्यम, या उच्च आय का है?",
        "ar": "هل حيك من أصحاب الدخل المنخفض أم المتوسط أم المرتفع؟",
    },
    "payday": {
        "en": "On which day(s) of the month do your customers usually get paid?",
        "ur": "مہینے کی کس تاریخ کو گاہکوں کو تنخواہ ملتی ہے؟",
        "es": "¿Qué día(s) del mes cobran normalmente sus clientes?",
        "sw": "Wateja wako hulipwa siku gani za mwezi?",
        "hi": "महीने की किस तारीख को ग्राहकों को वेतन मिलता है?",
        "ar": "في أي يوم من الشهر يتقاضى عملاؤك رواتبهم؟",
    },
    "nearby_anchors": {
        "en": "What is near your shop (school, market, mosque, bus stop, ...)?",
        "ur": "آپ کی دکان کے قریب کیا ہے (اسکول، بازار، مسجد، بس اسٹاپ)؟",
        "es": "¿Qué hay cerca de su tienda (escuela, mercado, mezquita, parada)?",
        "sw": "Ni kitu gani kilicho karibu na duka lako (shule, soko, msikiti)?",
        "hi": "आपकी दुकान के पास क्या है (स्कूल, बाजार, मस्जिद)?",
        "ar": "ما الذي يقع بالقرب من متجرك (مدرسة، سوق، مسجد)؟",
    },
    "shop_category": {
        "en": "What kind of shop is it (grocery, pharmacy, clothes, ...)?",
        "ur": "یہ کس قسم کی دکان ہے (کریانہ، فارمیسی، کپڑے)؟",
        "es": "¿Qué tipo de tienda es (abarrotes, farmacia, ropa)?",
        "sw": "Ni duka la aina gani (vyakula, dawa, nguo)?",
        "hi": "यह किस प्रकार की दुकान है (किराना, दवा, कपड़े)?",
        "ar": "ما نوع المتجر (بقالة، صيدلية، ملابس)؟",
    },
    "currency": {
        "en": "Which currency do you use (e.g. PKR, USD)?",
        "ur": "آپ کون سی کرنسی استعمال کرتے ہیں (جیسے PKR)؟",
        "es": "¿Qué moneda utiliza?", "sw": "Unatumia sarafu gani?",
        "hi": "आप कौन सी मुद्रा उपयोग करते हैं?", "ar": "ما العملة التي تستخدمها؟",
    },
    "budget": {
        "en": "What is your purchasing budget, and in which currency?",
        "ur": "آپ کا خریداری بجٹ کیا ہے اور کس کرنسی میں؟",
        "es": "¿Cuál es su presupuesto de compra y en qué moneda?",
        "sw": "Bajeti yako ya manunuzi ni kiasi gani?",
        "hi": "आपका खरीद बजट क्या है और किस मुद्रा में?",
        "ar": "ما ميزانية الشراء لديك وبأي عملة؟",
    },
    "language_detected": {
        "en": "Which language would you like me to reply in?",
        "ur": "آپ کس زبان میں جواب چاہتے ہیں؟", "es": "¿En qué idioma desea la respuesta?",
        "sw": "Ungependa jibu kwa lugha gani?", "hi": "आप किस भाषा में उत्तर चाहते हैं?",
        "ar": "بأي لغة تريد الرد؟",
    },
}


# --------------------------------------------------------------------------- #
# Language detection
# --------------------------------------------------------------------------- #

def detect_language(text: str) -> tuple[str, float]:
    t = (text or "").lower()
    arabic_chars = sum(1 for c in t if _SCRIPT["arabic"][0] <= ord(c) <= _SCRIPT["arabic"][1])
    deva_chars = sum(1 for c in t if _SCRIPT["devanagari"][0] <= ord(c) <= _SCRIPT["devanagari"][1])

    if deva_chars >= 3:
        return "hi", 0.9
    if arabic_chars >= 3:
        ar_hits = sum(1 for w in _LANG_SCRIPT_KW["ar"] if w in t)
        ur_hits = sum(1 for w in _LANG_SCRIPT_KW["ur"] if w in t)
        if ar_hits > ur_hits:
            return "ar", 0.85
        return "ur", 0.85

    words = set(re.findall(r"[a-z]+", t))
    scores = {lang: len(words & kws) for lang, kws in _ROMAN_LANG_KW.items() if lang != "en"}
    en_hits = len(words & _ROMAN_LANG_KW["en"])
    if scores:
        best_lang = max(scores, key=scores.get)
        if scores[best_lang] >= 2 and scores[best_lang] > en_hits:
            return best_lang, 0.75
    return "en", 0.6


# --------------------------------------------------------------------------- #
# Rule-based extraction (offline, deterministic)
# --------------------------------------------------------------------------- #

def _kw_in(text: str, kw: str) -> bool:
    """Word-boundary-aware keyword hit so 'small' does not match 'mall'."""
    return re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text) is not None


def _find_first(text: str, table) -> tuple[str | None, str | None]:
    for canonical, keywords in table:
        for kw in keywords:
            if _kw_in(text, kw):
                return canonical, kw
    return None, None


def _find_all(text: str, table) -> list[str]:
    out = []
    for canonical, keywords in table:
        if any(_kw_in(text, kw) for kw in keywords):
            out.append(canonical)
    return out


def _extract_payday(text: str, locale: str, today: date | None) -> tuple[list | None, float]:
    if not any(k in text for k in _PAYDAY_KW) and "end of the month" not in text \
            and "mahine ke aakhir" not in text and "fin de mes" not in text:
        return None, 0.0
    days: list[int] = []
    m = re.search(r"(?:payday|salary|tankha|تنخواہ|sueldo|pagos?|mshahara|راتب|वेतन)"
                  r"[^\d]{0,15}((?:\d{1,2}[^\d]{0,12}){1,3})", text)
    if m:
        for num in re.findall(r"\b(\d{1,2})\b", m.group(1)):
            n = int(num)
            if 1 <= n <= 31:
                days.append(n)
    for kw, token in (("end of the month", "last"), ("mahine ke aakhir", "last"),
                      ("fin de mes", "last"), ("مہینے کے آخر", "last"), ("نهاية الشهر", "last")):
        if kw in text:
            dr = normalize_date(kw, locale, today)
            if dr:
                days.append(int(dr.iso[-2:]))
    if not days:
        return None, 0.0
    return sorted(set(days)), 0.8


def _rule_extract(text: str, locale: str, today: date | None) -> dict:
    raw: dict[str, dict] = {}
    lang, lang_conf = detect_language(text)
    raw["language_detected"] = {"value": lang, "confidence": lang_conf}

    # shop_category
    cat, cat_kw = _find_first(text, _CATEGORY_KW)
    raw["shop_category"] = {"value": cat, "confidence": 0.9 if cat_kw and cat != "general_store"
                            else (0.5 if cat else 0.0)}

    # anchors
    anchors = _find_all(text, _ANCHOR_KW)
    raw["nearby_anchors"] = {"value": anchors or None, "confidence": 0.75 if anchors else 0.0}

    # location_type: gazetteer first, then keywords
    loc_conf = 0.0
    loc = None
    # look for known place names
    for candidate in _candidate_places(text):
        pm = resolve_place(candidate)
        if pm.matched:
            loc = pm.location_type
            loc_conf = pm.confidence
            if pm.kind and pm.kind in {a for a, _ in _ANCHOR_KW} and pm.kind not in anchors:
                anchors.append(pm.kind)
            break
    if loc is None:
        loc, kw = _find_first(text, _LOC_TYPE_KW)
        loc_conf = 0.5 if loc else 0.0
    raw["nearby_anchors"] = {"value": anchors or None,
                             "confidence": raw["nearby_anchors"]["confidence"] or (0.75 if anchors else 0.0)}
    raw["location_type"] = {"value": loc, "confidence": loc_conf}

    # income
    inc, _ = _find_first(text, _INCOME_KW)
    raw["income_band"] = {"value": inc, "confidence": 0.7 if inc else 0.0}

    # payday
    pdays, pconf = _extract_payday(text, locale, today)
    raw["payday"] = {"value": pdays, "confidence": pconf}

    # currency + budget
    money = normalize_money(text, locale)
    region = "south_asia_karachi"
    default_ccy = region_currency(region)
    currency = money.currency if (money and money.currency) else (
        default_ccy if lang in ("ur", "hi") else None)
    raw["currency"] = {"value": currency, "confidence": (0.9 if money and money.currency
                                                         else (0.55 if currency else 0.0))}

    budget = None
    bconf = 0.0
    bm = re.search(r"(budget|bajet|presupuesto|bajeti|بجٹ|ميزانية|बजट)[^\d]{0,15}([\d.,]+\s*\w*)", text, re.I)
    if bm:
        parsed = normalize_money(bm.group(2), locale)
        if parsed:
            budget, bconf = parsed.amount, 0.9
            if not raw["currency"]["value"] and parsed.currency:
                raw["currency"] = {"value": parsed.currency, "confidence": 0.8}
    raw["budget"] = {"value": budget, "confidence": bconf}

    return raw


def _candidate_places(text: str) -> list[str]:
    """Probe the whole text (word-boundary matches) plus individual word tokens."""
    words = re.findall(r"[A-Za-z\u0600-\u06ff\u0900-\u097f]{3,}", text)
    return [text, *words]


# --------------------------------------------------------------------------- #
# LLM extraction
# --------------------------------------------------------------------------- #

def _build_prompt(text: str, locale: str | None) -> list[dict]:
    # NB: the template contains literal JSON braces ({"value": ...}), so we must NOT
    # use str.format here. Targeted replacement leaves those braces intact.
    body = (_PROMPT
            .replace("{field_spec}", _FIELD_SPEC)
            .replace("{locale}", locale or "unspecified")
            .replace("{text}", text))
    return [
        {"role": "system", "content": "You output only valid JSON. You never estimate numbers."},
        {"role": "user", "content": body},
    ]


def _llm_extract(text: str, locale: str | None, client: LLMClient) -> dict:
    raw = client.complete(_build_prompt(text, locale), json_mode=True, max_tokens=600)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {}
    # allow both {"field": {...}} and {"fields": {"field": {...}}}
    return data.get("fields", data) if isinstance(data, dict) else {}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def extract_profile(
    text: str,
    *,
    locale: str | None = None,
    threshold: float | None = None,
    client: LLMClient | None = None,
    offline: bool | None = None,
    today: date | None = None,
    settings: Settings | None = None,
) -> Profile:
    """Extract a language-neutral Profile from a free-form shop description.

    ``offline=True`` (or backend == "mock") uses the deterministic rule extractor;
    otherwise the LLM is used. Both paths validate against the schema.
    """
    s = settings or get_settings()
    thr = s.confidence_threshold if threshold is None else threshold
    today = today or date.today()
    loc = locale or "en-PK"

    use_rules = offline if offline is not None else (s.backend == "mock")
    model_name = "RuleBasedExtractor"

    if use_rules:
        raw = _rule_extract(text, loc, today)
    else:
        try:
            active = client or get_default_client(s)
            raw = _llm_extract(text, locale, active)
            if not raw:  # unparseable / empty model output -> use the rule extractor
                raise ValueError("LLM returned no extractable fields")
            model_name = getattr(active, "name", "LLMClient")
        except Exception:
            # Never fail closed: fall back to the deterministic extractor.
            raw = _rule_extract(text, loc, today)
            model_name = "RuleBasedExtractor(fallback)"

    fields, issues = coerce_fields(raw)

    # The gazetteer is authoritative for KNOWN local places: an LLM often does not know
    # Karachi neighbourhoods. Apply it on both paths so location_type is consistent and
    # language-independent. Unknown places are left as-is (and may trigger a follow-up).
    for candidate in _candidate_places(text):
        pm = resolve_place(candidate)
        if pm.matched and pm.location_type:
            fields["location_type"] = FieldValue(
                value=pm.location_type,
                confidence=max(0.8, fields["location_type"].confidence))
            if pm.kind in {a for a, _ in _ANCHOR_KW}:
                anchors_now = list(fields["nearby_anchors"].value or [])
                if pm.kind not in anchors_now:
                    anchors_now.append(pm.kind)
                    fields["nearby_anchors"] = FieldValue(
                        value=anchors_now,
                        confidence=max(0.75, fields["nearby_anchors"].confidence))
            issues = [i for i in issues if i.field != "location_type"]
            break

    # Currency: an explicit currency token in the text is authoritative over the model's
    # guess (the LLM may return PKR for Hindi "रुपये" or omit e.g. Swahili "shillings").
    money = normalize_money(text, loc)
    if money and money.currency:
        fields["currency"] = FieldValue(
            value=money.currency, confidence=max(0.85, fields["currency"].confidence))
        issues = [i for i in issues if i.field != "currency"]

    # follow-ups: missing/invalid or low confidence
    follow_ups: list[FollowUp] = []
    src_lang = fields["language_detected"].value or (detect_language(text)[0])
    for name in EXTRACTION_FIELDS:
        fv = fields[name]
        issue = next((i for i in issues if i.field == name), None)
        if issue is not None:
            follow_ups.append(FollowUp(field=name,
                                       question=_question(name, src_lang),
                                       reason="missing"))
        elif fv.confidence < thr:
            follow_ups.append(FollowUp(field=name,
                                       question=_question(name, src_lang),
                                       reason="low_confidence"))

    audit_id = log_event("extract", {
        "model": model_name,
        "backend": "rule" if use_rules else "amd",
        "language": src_lang,
        "input_text": text,
        "output": {k: {"value": v.value, "confidence": v.confidence} for k, v in fields.items()},
        "guard_passed": None,
        "low_confidence_fields": [q.field for q in follow_ups],
        "prompt_sha256": sha256(text),
    }, settings=s)

    return Profile(
        fields=fields,
        follow_up_questions=follow_ups,
        needs_confirmation=bool(follow_ups),
        locale=loc,
        source_language=src_lang,
        text=text,
        audit_id=audit_id,
        model=model_name,
    )


def _question(field: str, lang: str) -> str:
    table = _FOLLOWUP_Q.get(field, {})
    return table.get(lang) or table.get("en") or f"Please provide a value for '{field}'."


def apply_corrections(profile: Profile, edits: dict, *, settings: Settings | None = None) -> Profile:
    """Apply retailer confirm/correct edits. Returns a NEW Profile.

    Edited fields get confidence 1.0 (human-confirmed); their follow-up questions are
    cleared and ``needs_confirmation`` recomputed. The change is written to the audit log.
    """
    fields = dict(profile.fields)
    applied: dict = {}
    for name, entry in edits.items():
        if name not in EXTRACTION_FIELDS:
            continue
        raw_val = entry.get("value") if isinstance(entry, dict) and "value" in entry else entry
        from .schemas import coerce_field
        coerced, ok = coerce_field(name, raw_val)
        if ok:
            fields[name] = FieldValue(value=coerced, confidence=1.0)
            applied[name] = coerced

    follow_ups = [q for q in profile.follow_up_questions if q.field not in applied]
    log_event("correction", {
        "audit_id": profile.audit_id,
        "corrections": applied,
        "input_text": profile.text,
    }, audit_id=profile.audit_id, settings=settings)

    return profile.model_copy(update={
        "fields": fields,
        "follow_up_questions": follow_ups,
        "needs_confirmation": bool(follow_ups),
    })
