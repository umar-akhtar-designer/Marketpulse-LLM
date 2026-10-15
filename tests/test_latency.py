"""Latency: the offline (deterministic) path must be fast.

The *agreed AMD latency budget* (extraction <= 8s, explanation <= 12s p50) applies to
the LIVE endpoint and is measured by ``scripts/measure_latency.py`` (requires credentials).
Here we assert the offline path is near-instant so CI is fast and deterministic.
"""

import time

from llm import explain, extract_profile
from mocks import get_mock_forecasts, get_mock_plan

_TEXT = "small grocery shop near a school in Liaquatabad, budget 30k rupees, payday 25"


def test_offline_extraction_is_fast():
    start = time.perf_counter()
    for _ in range(50):
        extract_profile(_TEXT, offline=True)
    elapsed = time.perf_counter() - start
    assert elapsed / 50 < 0.25, f"offline extraction too slow: {elapsed/50:.3f}s/call"


def test_offline_explanation_is_fast():
    plan, fc = get_mock_plan(), get_mock_forecasts()
    start = time.perf_counter()
    for _ in range(50):
        explain("Why fewer units?", plan, fc, "en", offline=True)
    elapsed = time.perf_counter() - start
    assert elapsed / 50 < 0.25, f"offline explanation too slow: {elapsed/50:.3f}s/call"
