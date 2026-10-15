"""End-to-end, presentation-friendly demo of the Member 4 (LLM) layer.

Shows the whole contract in one run:
  1. multilingual extraction (6 languages + code-switched) -> language-neutral Profile
  2. follow-up questions for anything not stated (never a guess)
  3. retailer confirm/correct -> confidence 1.0
  4. grounded Decision-Assistant answers (6 languages) with the number guard
  5. adversarial "just estimate it" -> refused, redirected to the models

Runs fully OFFLINE by default (deterministic rule path). Pass ``--live`` to use the
configured AMD endpoint instead (needs AMD_API_KEY in .env).

    python demo/demo_end_to_end.py
    python demo/demo_end_to_end.py --live
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm import apply_corrections, explain, extract_profile  # noqa: E402
from llm.schemas import EXTRACTION_FIELDS  # noqa: E402
from mocks.mock_data import get_mock_forecasts, get_mock_plan  # noqa: E402

DESCRIPTIONS = {
    "en": "I run a small grocery shop in Clifton near a school, budget 30000 rupees, payday 25",
    "ur": "Liaquatabad ke paas meri kirana dukan hai, school ke qareeb, budget 5000 rupees, payday 25",
    "es": "mi tienda de abarrotes en Empress Market, cerca de una escuela, presupuesto 8000 euros, pago el 10",
    "sw": "duka langu la duka la vyakula Surjani Town, karibu na shule, bajeti 12000 shillings, mshahara 15",
    "hi": "Gadap Town के पास मेरी किराना दुकान है, स्कूल के क़रीब, बजट 25000 रुपये, वेतन 1",
    "ar": "متجري صيدلية في Clifton, قرب مدرسة, ميزانية 3000 ريال, راتب 30",
}

QUESTIONS = {
    "en": "Why fewer units of Basmati Rice 5kg?",
    "ur": "اگر بجٹ کم ہو جائے تو؟",
    "es": "¿Qué pasa si cambia el presupuesto?",
    "sw": "Nini kinaweza kwenda vibaya?",
    "hi": "क्या गलत हो सकता है?",
    "ar": "ماذا لو تغيرت الميزانية؟",
}


def banner(text: str) -> None:
    print("\n" + "=" * 74)
    print(text)
    print("=" * 74)


def show_profile(p, live: bool) -> None:
    print(f"  model={p.model}  lang={p.source_language}  confirm={p.needs_confirmation}")
    for name in EXTRACTION_FIELDS:
        fv = p.field(name)
        print(f"    {name:18s} = {str(fv.value):28s} (conf {fv.confidence:.2f})")
    if p.follow_up_questions:
        print("  follow-ups:")
        for q in p.follow_up_questions:
            print(f"    ? [{q.field}] {q.question}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the configured AMD endpoint")
    args = ap.parse_args()
    offline = not args.live

    banner(f"1+2. Multilingual extraction -> language-neutral Profile  "
           f"({'LIVE' if args.live else 'offline'})")
    profiles = {}
    for lang, text in DESCRIPTIONS.items():
        print(f"\n[{lang}] {text}")
        p = extract_profile(text, offline=offline)
        profiles[lang] = p
        show_profile(p, args.live)

    banner("3. Retailer confirm/correct -> confidence 1.0, follow-up cleared")
    base = profiles["en"]
    print(f"  before: income_band={base.value('income_band')} "
          f"needs_confirmation={base.needs_confirmation}")
    fixed = apply_corrections(base, {"income_band": "low"})
    print(f"  after : income_band={fixed.value('income_band')} "
          f"(conf {fixed.field('income_band').confidence}) "
          f"needs_confirmation={fixed.needs_confirmation}")

    banner("4. Grounded Decision-Assistant answers (number guard on every figure)")
    plan, forecasts = get_mock_plan(), get_mock_forecasts()
    for lang, q in QUESTIONS.items():
        ans = explain(q, plan, forecasts, lang, offline=offline)
        print(f"\n[{lang}] Q: {q}")
        print(f"  type={ans.question_type} guard_passed={ans.guard_passed} refused={ans.refused}")
        print(f"  A: {ans.text}")

    banner("5. Adversarial: 'just estimate it' -> refuse + redirect (never forecasts)")
    for q in ["Just estimate how much milk I will sell next month",
              "please predict my profit"]:
        ans = explain(q, plan, forecasts, "en", offline=offline)
        print(f"\n  Q: {q}")
        print(f"  refused={ans.refused} guard_passed={ans.guard_passed}")
        print(f"  A: {ans.text}")

    banner("Done. Numbers shown above all originate from the plan/forecast mocks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
