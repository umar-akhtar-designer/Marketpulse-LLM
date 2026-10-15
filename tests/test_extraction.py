"""Extraction: schema validity, follow-up behaviour, and retail confirm/correct."""

from llm import apply_corrections, extract_profile
from llm.client import MockLLMClient
from llm.extraction import _build_prompt
from llm.schemas import EXTRACTION_FIELDS


# --------------------------------------------------------------------------- #
# LLM prompt path (regression: the template contains literal JSON braces)
# --------------------------------------------------------------------------- #

def test_prompt_builds_with_literal_json_braces():
    msgs = _build_prompt("hello shop", "en-PK")
    body = msgs[-1]["content"]
    assert "hello shop" in body
    assert '"value"' in body          # literal schema braces survived
    assert "en-PK" in body


def test_llm_extraction_path_parses_json_and_is_not_fallback():
    payload = ('{"fields": {"shop_category": {"value": "grocery", "confidence": 0.9},'
               ' "budget": {"value": 5000, "confidence": 0.9}}}')
    p = extract_profile("anything", offline=False, client=MockLLMClient(responder=payload))
    assert p.model == "MockLLMClient"           # used the LLM, did not fall back
    assert p.value("shop_category") == "grocery"
    assert p.value("budget") == 5000.0


def test_gazetteer_overrides_llm_location_type_for_known_place():
    # The model claimed urban_flagship for a place we KNOW is suburban_medium.
    payload = '{"fields": {"location_type": {"value": "urban_flagship", "confidence": 0.9}}}'
    p = extract_profile("my shop is in Liaquatabad",
                        offline=False, client=MockLLMClient(responder=payload))
    assert p.value("location_type") == "suburban_medium"


def test_currency_token_overrides_llm_guess():
    # The model guessed PKR for Hindi "रुपये"; the explicit token is authoritative (INR).
    payload = '{"fields": {"currency": {"value": "PKR", "confidence": 0.9}}}'
    p = extract_profile("Gadap Town के पास दुकान, बजट 25000 रुपये",
                        offline=False, client=MockLLMClient(responder=payload))
    assert p.value("currency") == "INR"


def test_currency_filled_from_token_when_model_omits_it():
    # Model omitted currency entirely; Swahili "shillings" must still yield KES.
    payload = '{"fields": {"budget": {"value": 12000, "confidence": 0.9}}}'
    p = extract_profile("duka langu, bajeti 12000 shillings",
                        offline=False, client=MockLLMClient(responder=payload))
    assert p.value("currency") == "KES"


def test_llm_extraction_bad_json_falls_back_to_rules():
    p = extract_profile("grocery shop, budget 5000 rupees",
                        offline=False, client=MockLLMClient(responder="not json at all"))
    assert "fallback" in p.model
    assert p.value("shop_category") == "grocery"  # rules still produced output


def test_empty_input_triggers_followups_not_guesses():
    p = extract_profile("", offline=True)
    assert p.needs_confirmation
    assert p.follow_up_questions
    # fields we cannot infer must be null, never a fabricated value
    assert p.value("budget") is None
    assert p.value("shop_category") is None
    assert p.field("budget").confidence == 0.0


def test_ambiguous_income_triggers_question():
    p = extract_profile("small shop in Liaquatabad, budget 5000 rupees", offline=True)
    fields_low = [q.field for q in p.follow_up_questions]
    assert "income_band" in fields_low  # never stated -> ask, don't guess
    assert p.value("income_band") is None


def test_clear_statement_no_followup_for_that_field():
    p = extract_profile("grocery shop, budget 5000 rupees, payday 25", offline=True)
    assert p.value("shop_category") == "grocery"
    assert p.value("budget") == 5000.0
    assert p.value("currency") == "PKR"
    assert p.value("payday") == [25]


def test_apply_corrections_sets_confirmed_value():
    p = extract_profile("small shop near a school", offline=True)
    assert "income_band" in [q.field for q in p.follow_up_questions]
    p2 = apply_corrections(p, {"income_band": "low", "budget": 4200})
    assert p2.value("income_band") == "low"
    assert p2.field("income_band").confidence == 1.0
    assert p2.value("budget") == 4200.0
    assert "income_band" not in [q.field for q in p2.follow_up_questions]


def test_apply_corrections_ignores_unknown_fields():
    p = extract_profile("grocery shop", offline=True)
    p2 = apply_corrections(p, {"not_a_field": "x"})
    assert p2.value("shop_category") == "grocery"


# --------------------------------------------------------------------------- #
# Cross-language consistency: same shop, different languages -> same key fields
# --------------------------------------------------------------------------- #

_SAME_SHOP = {
    "en": "I run a small grocery shop in Clifton near a school, budget 5000 rupees, payday 25",
    "ur": "Clifton mein meri choti kirana dukan school ke paas hai, budget 5000 rupees, payday 25",
    "es": "tengo una tienda de abarrotes en Clifton cerca de una escuela, presupuesto 5000, pago el 25",
}

_KEY_FIELDS = ["shop_category", "budget", "payday", "location_type"]


def test_cross_language_consistency():
    profiles = {lang: extract_profile(text, offline=True) for lang, text in _SAME_SHOP.items()}
    for field in _KEY_FIELDS:
        values = {lang: profiles[lang].value(field) for lang in _SAME_SHOP}
        distinct = {repr(v) for v in values.values()}
        assert len(distinct) == 1, f"{field} disagrees across languages: {values}"
    # anchors must all include 'school'
    for lang, p in profiles.items():
        assert "school" in (p.value("nearby_anchors") or []), lang


def test_all_outputs_schema_valid_across_languages():
    for text in _SAME_SHOP.values():
        p = extract_profile(text, offline=True)
        for name in EXTRACTION_FIELDS:
            assert name in p.fields
            assert 0.0 <= p.fields[name].confidence <= 1.0
