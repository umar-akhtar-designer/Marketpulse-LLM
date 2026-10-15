"""Quality gate: run the eval harness and assert minimum extraction quality.

The committed eval set (eval/descriptions.jsonl) is scored here so a regression in the
keyword tables / normalizers / gazetteer fails CI. All numbers are produced by
eval/harness.py - this test only sets the pass/fail bar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.harness import run  # noqa: E402


@pytest.fixture(scope="module")
def report():
    return run(live=False)


def test_schema_validity_is_total(report):
    assert report["schema_validity"] == 1.0


def test_core_language_accuracy(report):
    for lang, acc in report["per_language_core"].items():
        assert acc is not None and acc >= 0.9, f"{lang}: {acc}"


def test_low_resource_accuracy_floor(report):
    for lang, acc in report["per_language_low_resource"].items():
        assert acc is not None and acc >= 0.7, f"{lang}: {acc}"


def test_cross_language_consistency(report):
    assert report["cross_language_consistency"] >= 0.8


def test_high_confidence_predictions_are_reliable(report):
    c = report["calibration"]
    assert c["high_conf_n"] > 0
    assert c["high_conf_accuracy"] >= 0.8
    # if any low-confidence predictions exist, they must not beat the high bucket
    if c["low_conf_accuracy"] is not None:
        assert c["high_conf_accuracy"] >= c["low_conf_accuracy"]
