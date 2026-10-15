"""Pick the AMD-hosted model for MarketPulse AI by measuring, not guessing.

Runs the SAME extraction eval set (eval/descriptions.jsonl) against each candidate
model on the AMD endpoint and reports field accuracy + latency, then recommends the
best model that meets the latency budget (CONTRACT.md: extraction <= 8s p50).

    # discover ids first:
    python scripts/list_models.py
    # then compare the ones you care about:
    python scripts/model_selection.py --models "DeepSeek-V4-Flash,Model-A,Model-B"
    python scripts/model_selection.py --models "..." --limit 20

Requires AMD_BASE_URL + AMD_API_KEY (env or .env). If a model does not serve JSON
mode it is retried without it (see AMDClient).
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

from llm.client import AMDClient  # noqa: E402
from llm.config import get_settings  # noqa: E402
from llm.extraction import extract_profile  # noqa: E402
from eval.harness import SCORED, _correct  # noqa: E402

EVAL = ROOT / "eval" / "descriptions.jsonl"
LATENCY_BUDGET_P50 = 8.0


def evaluate(model: str, items: list[dict], deadline: float | None = None) -> dict:
    s = get_settings()
    client = AMDClient(s, model=model)
    correct = pred = 0
    latencies: list[float] = []
    errors = 0
    for idx, it in enumerate(items):
        if deadline is not None and time.perf_counter() > deadline:
            print(f"  [budget] stopping {model} early at item {idx}/{len(items)}", flush=True)
            break
        t0 = time.perf_counter()
        try:
            prof = extract_profile(it["text"], offline=False, client=client)
        except Exception:
            errors += 1
            print(f"  item {idx + 1}/{len(items)} ERROR", flush=True)
            continue
        dt = time.perf_counter() - t0
        latencies.append(dt)
        print(f"  item {idx + 1}/{len(items)} {dt:.1f}s", flush=True)
        for field in SCORED:
            gold = it["gold"].get(field)
            if gold is None:
                continue
            ok = _correct(field, prof.value(field), gold)
            if ok is None:
                continue
            pred += 1
            correct += int(ok)
    p50 = statistics.median(latencies) if latencies else float("nan")
    return {
        "model": model,
        "accuracy": round(correct / pred, 4) if pred else 0.0,
        "latency_p50_s": round(p50, 2),
        "latency_p90_s": round(statistics.quantiles(latencies, n=10)[8], 2) if len(latencies) > 2 else round(p50, 2),
        "n": pred,
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated model ids")
    ap.add_argument("--limit", type=int, default=0, help="cap eval items")
    ap.add_argument("--budget-s", type=float, default=0.0,
                    help="overall wall-clock budget in seconds (0 = unlimited)")
    args = ap.parse_args()

    s = get_settings()
    if not s.has_live_credentials:
        print("[!] No live credentials. Set AMD_API_KEY/AMD_BASE_URL in .env.")
        return 2

    items = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        items = items[: args.limit]

    deadline = (time.perf_counter() + args.budget_s) if args.budget_s > 0 else None
    results = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"evaluating {model} over {len(items)} items...", flush=True)
        results.append(evaluate(model, items, deadline=deadline))

    results.sort(key=lambda r: (-r["accuracy"], r["latency_p50_s"]))
    eligible = [r for r in results if r["latency_p50_s"] <= LATENCY_BUDGET_P50]

    print("\nmodel                          acc     p50(s)  p90(s)  n    err")
    for r in results:
        print(f"{r['model']:30s} {r['accuracy']:.2%}  {r['latency_p50_s']:6.2f}  "
              f"{r['latency_p90_s']:6.2f}  {r['n']:4d} {r['errors']:3d}")

    if eligible:
        best = eligible[0]
        print(f"\nRECOMMENDED: {best['model']}  "
              f"(acc {best['accuracy']:.2%}, p50 {best['latency_p50_s']}s <= {LATENCY_BUDGET_P50}s)")
        print(f"Set AMD_MODEL={best['model']} in .env")
        return 0
    print("\n[!] No candidate met the p50 latency budget; widen the candidate set.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
