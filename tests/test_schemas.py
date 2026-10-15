"""Schema validity: every output parses and validates against the schema.

Invariant: no invalid or guessed value can survive ``coerce_fields``. Anything that does
not conform to the controlled vocabularies is nulled and reported.
"""

import pytest

from llm.schemas import (
    EXTRACTION_FIELDS,
    INCOME_BANDS,
    LANGUAGES,
    LOCATION_TYPES,
    NEARBY_ANCHORS,
    SHOP_CATEGORIES,
    Profile,
    coerce_field,
    coerce_fields,
)

MESSY_RAW_OUTPUTS = [
    {"location_type": {"value": "URBAN-FLAGSHIP", "confidence": 0.9}},          # case/sep
    {"income_band": "wealthy"},                                                # out of vocab
    {"payday": [25, 30, 99, "last"]},                                          # out of range + token
    {"nearby_anchors": "school"},                                              # scalar not list
    {"nearby_anchors": ["school", "spaceship", "school"]},                     # bad + dup
    {"shop_category": "grocery"},                                              # scaalar ok
    {"currency": "pkr"},                                                       # lowercase -> upper
    {"currency": "rupees"},                                                    # not ISO
    {"budget": "5000"},                                                        # string number
    {"budget": -5},                                                            # negative
    {"language_detected": {"value": "UR", "confidence": 2.0}},                 # conf clamp
    {},                                                                        # empty
    {"location_type": None, "budget": None},
]


@pytest.mark.parametrize("raw", MESSY_RAW_OUTPUTS)
def test_coerce_never_yields_invalid_value(raw):
    fields, _issues = coerce_fields(raw)
    assert set(fields).issubset(set(EXTRACTION_FIELDS))
    for name, fv in fields.items():
        assert 0.0 <= fv.confidence <= 1.0
        if fv.value is not None:
            assert (coerce_field(name, fv.value)[1] is True), f"{name}={fv.value!r} not canonical"


def test_profile_from_plain_always_parses():
    p = Profile(fields=coerce_fields({"shop_category": "grocery"})[0])
    plain = p.to_plain()
    assert Profile(**{**plain}).fields["shop_category"].value == "grocery"


@pytest.mark.parametrize("value", list(LOCATION_TYPES))
def test_location_type_enum_accepted(value):
    assert coerce_field("location_type", value) == (value, True)


@pytest.mark.parametrize("value", list(INCOME_BANDS) + list(SHOP_CATEGORIES) + list(LANGUAGES))
def test_other_enums_accepted(value):
    # each value belongs to exactly one enum; at least one field must accept it
    assert any(coerce_field(f, value)[1] for f in
               ("income_band", "shop_category", "language_detected"))


@pytest.mark.parametrize("value", list(NEARBY_ANCHORS))
def test_anchor_vocab_accepted(value):
    assert coerce_field("nearby_anchors", [value]) == ([value], True)
