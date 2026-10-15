"""Local geography: gazetteer maps places -> location types; unknown -> follow-up."""

import pytest

from llm.gazetteer import available_regions, resolve_place


@pytest.mark.parametrize("name,expected_loc", [
    ("Liaquatabad", "suburban_medium"),
    ("Clifton Block 5", "urban_flagship"),
    ("Empress Market", "urban_flagship"),
    ("Gadap Town", "rural_kiosk"),
    ("Surjani Town", "rural_kiosk"),
])
def test_known_places(name, expected_loc):
    m = resolve_place(name)
    assert m.matched, name
    assert m.location_type == expected_loc


def test_fuzzy_match_typo():
    m = resolve_place("liaqatabad")  # typo
    assert m.matched
    assert m.location_type == "suburban_medium"


def test_unknown_place_returns_no_guess():
    m = resolve_place("Atlantis Boulevard")
    assert not m.matched
    assert m.location_type is None
    assert m.confidence == 0.0


def test_empty_input_no_match():
    assert not resolve_place("").matched


def test_regions_listed():
    assert "south_asia_karachi" in available_regions()
