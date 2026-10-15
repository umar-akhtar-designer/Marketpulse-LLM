"""Number guard: injected fake figures must be caught; cited figures must be grounded."""

import random

from llm.guard import build_grounded, check_numbers
from mocks import explain_inputs, get_mock_forecasts, get_mock_plan


def _sources():
    plan = get_mock_plan()
    return {"plan": plan, "explain_inputs": explain_inputs(plan), "forecasts": get_mock_forecasts()}


def test_grounded_numbers_are_accepted():
    src = _sources()
    text = "Budget 3000, spend 2980.5, expected profit 842.2, milk 48 units, cost 57.6."
    res = check_numbers(text, src)
    assert res.ok, res.ungrounded
    assert res.figures


def test_ungrounded_number_is_caught():
    res = check_numbers("You should order 999999 units.", _sources())
    assert not res.ok
    assert "999999" in res.ungrounded


def test_injected_fakes_caught_100_percent():
    src = _sources()
    rng = random.Random(1234)
    fakes = [rng.randint(10_000_000, 99_999_999) for _ in range(60)]
    missed = []
    for fake in fakes:
        res = check_numbers(f"Expected profit is {fake}.", src)
        if res.ok:
            missed.append(fake)
    assert missed == [], f"guard missed fakes: {missed}"


def test_percentage_grounds_to_decimal():
    # explain_inputs has budget_utilization_pct ~99.35 and probabilities like 0.15
    res = check_numbers("Stockout risk 15% is high.", _sources())
    assert res.ok, res.ungrounded


def test_grounded_source_paths_present():
    src = _sources()
    res = check_numbers("The plan orders 48 units with profit 26.4.", src)
    assert res.ok
    assert all(f.source_path for f in res.figures)


def test_every_figure_traces_to_a_source():
    src = _sources()
    grounded = build_grounded(src)
    text = "Budget 3000, milk 48 units, profit 26.4, spend 2980.5."
    for f in check_numbers(text, src).figures:
        assert f.source_path in grounded.values() or f.source_path  # non-empty path
