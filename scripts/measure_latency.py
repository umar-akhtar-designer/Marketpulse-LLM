"""Measure LIVE end-to-end latency of extraction and explanation.

The agreed budget (CONTRACT.md) is:
    * extraction   <= 8s  p50
    * explanation  <= 12s p50

This script hits the configured AMD endpoint. The offline (rule) path used by tests is
near-instant and is asserted in tests/test_latency.py instead.

    python scripts/measure_latency.py            # 1 pass over the eval set
    python scripts/measure_latency.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.config import get_settings  # noqa: E402
from llm.explainer import explain  # noqa: E402
from llm.extraction import extract_profile  # noqa: E402
from mocks.mock_data import get_mock_forecasts, get_mock_plan  # noqa: E402

EVAL = ROOT / "eval" / "descriptions.jsonl"
BUDGET = {"extraction": 8.0, "explanation": 12.0}


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def _report(name: str, xs: list[float]) -> bool:
    p50, p90, mx = _pct(xs, 50), _pct(xs, 90), max(xs)
    ok = p50 <= BUDGET[name]
    print(f"  {name:12s} n={len(xs):3d}  p50={p50:6.2f}s  p90={p90:6.2f}s  max={mx:6.2f}s  "
          f"budget(p50)<={BUDGET[name]:.0f}s  -> {'OK' if ok else 'OVER'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap number of eval items")
    args = ap.parse_args()

    s = get_settings()
    if not s.has_live_credentials:
        print("[!] No live credentials. Set AMD_API_KEY/AMD_BASE_URL in .env.")
        print("    (Offline latency is covered by tests/test_latency.py.)")
        return 2

    items = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        items = items[: args.limit]

    plan, forecasts = get_mock_plan(), get_mock_forecasts()
    questions = ["Why fewer units?", "What if the budget changes?", "What could go wrong?"]

    ext, exp = [], []
    print(f"Measuring LIVE latency via {s.base_url} (model={s.model}), {len(items)} items...")
    for it in items:
        t0 = time.perf_counter()
        extract_profile(it["text"], offline=False)
        ext.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        explain(questions[len(exp) % len(questions)], plan, forecasts, it["lang"], offline=False)
        exp.append(time.perf_counter() - t0)

    ok = _report("extraction", ext) and _report("explanation", exp)
    print("\nRESULT:", "PASS" if ok else "BEHIND BUDGET")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
