"""Score the extraction layer against the generated eval set.

Reports, in one run:
  * schema validity (every output is a valid ``Profile``)
  * per-field accuracy + coverage
  * per-language accuracy (with the low-resource languages flagged)
  * confidence calibration (are high-confidence fields more often correct?)
  * cross-language consistency (same shop described in 6 languages -> same fields)

    python eval/harness.py            # offline / deterministic (default)
    python eval/harness.py --live     # use the configured AMD endpoint

Writes eval/out/report.json and eval/out/report.md (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from llm.extraction import extract_profile  # noqa: E402
from llm.schemas import EXTRACTION_FIELDS, Profile  # noqa: E402

ITEMS = HERE / "descriptions.jsonl"
OUT = HERE / "out"

SCORED = ["shop_category", "budget", "currency", "payday", "location_type", "nearby_anchors"]
LOW_RESOURCE = {"sw", "hi", "ar"}


def _correct(field: str, pred, gold) -> bool | None:
    if pred is None:
        return None  # abstained -> not counted as correct or wrong
    if field == "budget":
        return abs(float(pred) - float(gold)) < 0.01
    if field == "payday":
        try:
            return set(int(x) for x in pred) == set(int(x) for x in gold)
        except (TypeError, ValueError):
            return False
    if field == "nearby_anchors":
        return set(gold).issubset(set(pred))
    return pred == gold


def run(live: bool = False, limit: int = 0, progress: bool = False) -> dict:
    items = [json.loads(line) for line in ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        items = items[:limit]

    per_field = {f: {"correct": 0, "pred": 0} for f in SCORED}
    per_lang: dict[str, dict] = {}
    hi_conf = {"correct": 0, "n": 0}
    lo_conf = {"correct": 0, "n": 0}
    schema_valid = 0
    groups: dict[str, dict] = {}
    threshold = 0.6

    for i, it in enumerate(items):
        if progress:
            print(f"\r[{i + 1}/{len(items)}] {it['id']:<14}", end="", flush=True)
        prof: Profile = extract_profile(it["text"], offline=not live)
        schema_valid += int(isinstance(prof, Profile) and
                            all(f in prof.fields for f in EXTRACTION_FIELDS))
        lang = it["lang"]
        per_lang.setdefault(lang, {"correct": 0, "pred": 0, "items": 0})
        per_lang[lang]["items"] += 1
        groups.setdefault(it["spec_id"], {})[lang] = {f: prof.value(f) for f in SCORED}

        for field in SCORED:
            gold = it["gold"].get(field)
            if gold is None:
                continue
            pred = prof.value(field)
            ok = _correct(field, pred, gold)
            if ok is None:
                continue
            per_field[field]["pred"] += 1
            per_lang[lang]["pred"] += 1
            if ok:
                per_field[field]["correct"] += 1
                per_lang[lang]["correct"] += 1
            conf = prof.field(field).confidence
            bucket = hi_conf if conf >= threshold else lo_conf
            bucket["n"] += 1
            bucket["correct"] += int(ok)

    def acc(d):
        return round(d["correct"] / d["pred"], 4) if d["pred"] else None

    # cross-language consistency: language-independent fields must agree across all
    # 7 renderings. Currency is excluded on purpose: each language's sentence states a
    # different currency word (PKR/EUR/KES/INR/SAR), so it is expected to differ.
    key_fields = ["shop_category", "budget", "payday", "location_type"]
    consistent = 0
    for spec_id, by_lang in groups.items():
        ok = True
        for f in key_fields:
            vals = {json.dumps(by_lang[l][f], sort_keys=True) for l in by_lang if by_lang[l][f] is not None}
            if len(vals) > 1:
                ok = False
        consistent += int(ok)

    report = {
        "items": len(items),
        "live": live,
        "schema_validity": round(schema_valid / len(items), 4),
        "per_field": {f: {"accuracy": acc(v), "coverage": round(v["pred"] / len(items), 4)}
                      for f, v in per_field.items()},
        "per_language": {l: {"accuracy": acc(v), "items": v["items"]}
                         for l, v in sorted(per_lang.items())},
        "per_language_core": {l: acc(v) for l, v in per_lang.items() if l not in LOW_RESOURCE},
        "per_language_low_resource": {l: acc(v) for l, v in per_lang.items() if l in LOW_RESOURCE},
        "calibration": {
            "threshold": threshold,
            "high_conf_accuracy": round(hi_conf["correct"] / hi_conf["n"], 4) if hi_conf["n"] else None,
            "high_conf_n": hi_conf["n"],
            "low_conf_accuracy": round(lo_conf["correct"] / lo_conf["n"], 4) if lo_conf["n"] else None,
            "low_conf_n": lo_conf["n"],
        },
        "cross_language_consistency": round(consistent / len(groups), 4),
    }
    return report


def _md(r: dict) -> str:
    lines = [f"# Extraction eval report {'(LIVE)' if r['live'] else '(offline)'}", "",
             f"- items: **{r['items']}**",
             f"- schema validity: **{r['schema_validity']:.0%}**",
             f"- cross-language consistency: **{r['cross_language_consistency']:.0%}**", "",
             ("> Note: on the **offline** path the rule extractor is tuned to these templates, so 100% is "
              "expected; the moment of truth is the **live** LLM path "
              "(`--live`, see docs/MODEL_SELECTION.md)." if not r["live"] else
              "> This is the **live** LLM path (the model actually did the extraction)."),
             "", "## Per-field", "", "| field | accuracy | coverage |", "|---|---|---|"]
    for f, v in r["per_field"].items():
        a = "n/a" if v["accuracy"] is None else f"{v['accuracy']:.0%}"
        lines.append(f"| {f} | {a} | {v['coverage']:.0%} |")
    lines += ["", "## Per-language", "", "| lang | accuracy | items |", "|---|---|---|"]
    for l, v in r["per_language"].items():
        a = "n/a" if v["accuracy"] is None else f"{v['accuracy']:.0%}"
        tag = " (low-resource)" if l in LOW_RESOURCE else ""
        lines.append(f"| {l}{tag} | {a} | {v['items']} |")
    c = r["calibration"]
    lines += ["", "## Calibration", "",
              f"- high confidence (>= {c['threshold']}): "
              f"{c['high_conf_accuracy'] if c['high_conf_accuracy'] is not None else 'n/a'} "
              f"over {c['high_conf_n']} predictions",
              f"- low confidence (< {c['threshold']}): "
              f"{c['low_conf_accuracy'] if c['low_conf_accuracy'] is not None else 'n/a'} "
              f"over {c['low_conf_n']} predictions"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the configured AMD endpoint")
    ap.add_argument("--limit", type=int, default=0, help="cap number of eval items")
    args = ap.parse_args()
    report = run(live=args.live, limit=args.limit, progress=args.live)
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text(_md(report), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}/report.json and {OUT}/report.md")


if __name__ == "__main__":
    main()
