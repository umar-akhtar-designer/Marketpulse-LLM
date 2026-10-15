"""Component E - grounded AI Decision Assistant.

``explain(question, plan, forecasts, lang) -> Answer``

Retrieval -> routing -> generation (LLM or deterministic template) -> number guard.
The LLM may phrase the answer, but every number must come from the optimizer / forecast
output. Ungrounded output is rejected and a safe, fully-grounded fallback is returned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .audit import log_event
from .client import LLMClient, get_default_client
from .config import Settings, get_settings
from .guard import check_numbers
from .schemas import Answer

_PROMPT = (Path(__file__).resolve().parent / "prompts" / "explain.txt").read_text(encoding="utf-8")

_ROUTES: list[tuple[str, list[str]]] = [
    ("what_if_budget", ["what if", "if the budget", "if budget", "budget change", "budget was",
                        "budget were", "reduce budget", "increase budget", "lower budget",
                        "higher budget", "agar budget", "agr budget", "si el presupuesto",
                        "si cambia el presupuesto", "cambia el presupuesto", "pasa si",
                        "bajeti ikiwa", "إذا تغيرت الميزانية", "إذا كانت الميزانية",
                        "لو تغيرت الميزانية", "تغيرت الميزانية", "ماذا لو تغيرت",
                        "अगर बजट", "اگر بجٹ"]),
    ("why_excluded", ["why not", "why excluded", "left out", "dropped", "excluded", "omit",
                      "kyun nahi", "kyu nahi", "shamil nahi", "por que no", "kwa nini haiku",
                      "لماذا لم", "لماذا لا", "क्यों नहीं", "کیوں نہیں", "شامل نہیں"]),
    ("what_could_be_wrong", ["what could go wrong", "what might go wrong", "go wrong", "risk",
                             "uncertain", "khatra", "kya ghalat", "que puede salir mal",
                             "nini kinaweza", "kosa", "ما الذي قد يخطئ", "क्या गलत",
                             "کیا غلط", "خطرہ", "غير يقيني"]),
    ("why_fewer_units", ["why fewer", "why so few", "fewer units", "less units", "so little",
                         "why did you reduce", "reduce the quantity", "kam kyun", "kam kyu",
                         "kam units", "por que menos", "kwa nini chache", "لماذا اقل",
                         "لماذا أقل", "कम क्यों", "کم کیوں", "کم کیو", "کم تعداد"]),
]
_ESTIMATE_KW = ["just estimate", "estimate", "guess", "predict", "roughly", "approximately",
                "approx", "andaza", "andaza lagao", "anuman", "estima", "kadiria",
                "قدّر", "تقدير", "अनुमान"]

_REASON_LOC = {
    "ALLOCATED_OPTIMAL": {"en": "it is funded to its optimal quantity.",
                          "ur": "اسے اس کی بہترین مقدار تک خریدا گیا ہے۔",
                          "es": "se financia en su cantidad óptima.",
                          "sw": "kimenunuliwa kwa kiwango bora.", "hi": "इसे इसकी इष्टतम मात्रा तक खरीदा गया है।",
                          "ar": "تم تمويله بكميته المثلى."},
    "ALLOCATED_HIGH_MARGIN": {"en": "it has a high margin and reliable demand.",
                              "ur": "اس پر منافع زیادہ ہے اور طلب بھروسے مند ہے۔",
                              "es": "tiene un buen margen y demanda confiable.", "sw": "ina faida kubwa na mahitaji imara.",
                              "hi": "इसका मार्जिन अच्छा और मांग भरोसेमंद है।", "ar": "هامشه مرتفع وطلبه مستقر."},
    "ALLOCATED_TRIMMED_BUDGET": {"en": "the quantity was trimmed because the budget is limited.",
                                 "ur": "بجٹ محدود ہونے کی وجہ سے مقدار کم کر دی گئی۔",
                                 "es": "la cantidad se redujo porque el presupuesto es limitado.",
                                 "sw": "kiwango kilipunguzwa kwa sababu bajeti ni ndogo.",
                                 "hi": "बजट सीमित होने के कारण मात्रा घटाई गई।",
                                 "ar": "تم تقليل الكمية لأن الميزانية محدودة."},
    "PACK_SIZE_ROUNDED": {"en": "it was rounded to the supplier pack size.",
                          "ur": "اسے سپلائر کے پیک سائز کے مطابق گول کیا گیا۔",
                          "es": "se redondeó al tamaño de paquete del proveedor.",
                          "sw": "ilizungushwa kwa saizi ya furushi ya msambazaji.",
                          "hi": "इसे आपूर्तिकर्ता पैक आकार तक पूर्णांकित किया गया।",
                          "ar": "تم تقريبه إلى كميات التغليف لدى المورد."},
    "MOQ_PROMOTED": {"en": "it was raised to the supplier minimum order quantity.",
                     "ur": "اسے سپلائر کی کم سے کم مقدار تک بڑھایا گیا۔",
                     "es": "se elevó al mínimo de pedido del proveedor.",
                     "sw": "ilipandishwa hadi kiwango cha chini cha agizo.",
                     "hi": "इसे आपूर्तिकर्ता की न्यूनतम मात्रा तक बढ़ाया गया।",
                     "ar": "تم رفعه إلى الحد الأدنى لكمية الطلب."},
    "DROPPED_HIGH_UNCERTAINTY": {"en": "its demand uncertainty is too high for a safe order.",
                                 "ur": "اس کی طلب میں غیر یقینی صورتحال بہت زیادہ ہے۔",
                                 "es": "su incertidumbre de demanda es demasiado alta.",
                                 "sw": "kutokuwa na uhakika wa mahitaji ni juu sana.",
                                 "hi": "इसकी मांग में अनिश्चितता बहुत अधिक है।",
                                 "ar": "عدم اليقين في الطلب مرتفع جداً."},
    "DROPPED_LOW_CAPITAL_EFFICIENCY": {"en": "its expected profit per currency unit is low.",
                                       "ur": "فی کرنسی منافع کم ہے۔",
                                       "es": "su beneficio por unidad de moneda es bajo.",
                                       "sw": "faida kwa kila kitengo cha fedha ni ndogo.",
                                       "hi": "प्रति इकाई लाभ कम है।",
                                       "ar": "الربح المتوقع لكل وحدة نقدية منخفض."},
    "DROPPED_BUDGET_EXHAUSTED": {"en": "the budget ran out before it could be funded.",
                                 "ur": "بجٹ ختم ہو گیا اس سے پہلے کہ اسے خریدا جا سکے۔",
                                 "es": "el presupuesto se agotó antes de financiarlo.",
                                 "sw": "bajeti iliisha kabla ya kununuliwa.",
                                 "hi": "इसे खरीदने से पहले बजट समाप्त हो गया।",
                                 "ar": "نفدت الميزانية قبل تمويله."},
    "CAPPED_SHELF_LIFE": {"en": "the quantity was capped to avoid spoilage.",
                          "ur": "خرابی سے بچنے کے لیے مقدار محدود رکھی گئی۔",
                          "es": "la cantidad se limitó para evitar el deterioro.",
                          "sw": "kiwango kilipunguzwa kuepuka kuharibika.",
                          "hi": "खराब होने से बचने के लिए मात्रा सीमित की गई।",
                          "ar": "تم تحديد الكمية لتفادي التلف."},
}

_T = {
    "why_fewer_units": {
        "en": "{name}: the plan orders {qty} units. {reason} Expected profit {profit}, stockout risk {stockout}.",
        "ur": "{name}: منصوبہ {qty} یونٹ آرڈر کرتا ہے۔ {reason} متوقع منافع {profit}، اسٹاک آؤٹ خطرہ {stockout}۔",
        "es": "{name}: el plan pide {qty} unidades. {reason} Beneficio esperado {profit}, riesgo de agotamiento {stockout}.",
        "sw": "{name}: mpango unaagiza vipimo {qty}. {reason} Faida inayotarajiwa {profit}, hatari ya kuisha {stockout}.",
        "hi": "{name}: योजना {qty} इकाइयाँ ऑर्डर करती है। {reason} अपेक्षित लाभ {profit}, स्टॉकआउट जोखिम {stockout}।",
        "ar": "{name}: تطلب الخطة {qty} وحدة. {reason} الربح المتوقع {profit}، خطر نفاد المخزون {stockout}.",
    },
    "what_if_budget": {
        "en": "If the budget is {b80}, expected profit is {p80}. At {b100} it is {p100}.",
        "ur": "اگر بجٹ {b80} ہو تو متوقع منافع {p80} ہے۔ {b100} پر یہ {p100} ہے۔",
        "es": "Si el presupuesto es {b80}, el beneficio esperado es {p80}. Con {b100} es {p100}.",
        "sw": "Ikiwa bajeti ni {b80}, faida inayotarajiwa ni {p80}. Kwa {b100} ni {p100}.",
        "hi": "यदि बजट {b80} हो तो अपेक्षित लाभ {p80} है। {b100} पर यह {p100} है।",
        "ar": "إذا كانت الميزانية {b80} فالربح المتوقع {p80}. عند {b100} يصبح {p100}.",
    },
    "what_could_be_wrong": {
        "en": "Main risk: {name}, with relative uncertainty {ru}. {note}",
        "ur": "بنیادی خطرہ: {name}، نسبتاً غیر یقینی {ru}۔ {note}",
        "es": "Riesgo principal: {name}, con incertidumbre relativa {ru}. {note}",
        "sw": "Hatari kuu: {name}, kutokuwa na uhakika {ru}. {note}",
        "hi": "मुख्य जोखिम: {name}, सापेक्ष अनिश्चितता {ru}। {note}",
        "ar": "الخطر الرئيسي: {name}، عدم يقين نسبي {ru}. {note}",
    },
    "why_excluded": {
        "en": "{name} was not ordered: {reason} Its unit cost is {cost}.",
        "ur": "{name} آرڈر نہیں کیا گیا: {reason} اس کی فی یونٹ لاگت {cost} ہے۔",
        "es": "{name} no se pidió: {reason} Su costo unitario es {cost}.",
        "sw": "{name} haikuagizwa: {reason} Gharama kwa kimo ni {cost}.",
        "hi": "{name} ऑर्डर नहीं किया गया: {reason} इसकी इकाई लागत {cost} है।",
        "ar": "لم يتم طلب {name}: {reason} تكلفة الوحدة {cost}.",
    },
    "general": {
        "en": "Budget {budget}, planned spend {spend}, expected profit {profit}. {funded} products funded, {dropped} not.",
        "ur": "بجٹ {budget}، متوقع خرچ {spend}، متوقع منافع {profit}۔ {funded} مصنوعات خریدی گئیں، {dropped} نہیں۔",
        "es": "Presupuesto {budget}, gasto previsto {spend}, beneficio esperado {profit}. {funded} productos financiados, {dropped} no.",
        "sw": "Bajeti {budget}, matumizi {spend}, faida {profit}. Bidhaa {funded} zimenunuliwa, {dropped} hazikununuliwa.",
        "hi": "बजट {budget}, नियोजित खर्च {spend}, अपेक्षित लाभ {profit}। {funded} उत्पाद खरीदे गए, {dropped} नहीं।",
        "ar": "الميزانية {budget}، الإنفاق المخطط {spend}، الربح المتوقع {profit}. تم تمويل {funded} منتج، و{dropped} لا.",
    },
    "refuse": {
        "en": "I can't estimate demand myself - the forecast comes from the demand model. For {name}, the plan orders {qty} units.",
        "ur": "میں خود طلب کا اندازہ نہیں لگا سکتا — پیش گوئی ڈیمانڈ ماڈل سے آتی ہے۔ {name} کے لیے منصوبہ {qty} یونٹ آرڈر کرتا ہے۔",
        "es": "No puedo estimar la demanda yo mismo: la previsión viene del modelo. Para {name}, el plan pide {qty} unidades.",
        "sw": "Siwezi kukisia mahitaji - utabiri unatoka kwa modeli. Kwa {name}, mpango unaagiza vipimo {qty}.",
        "hi": "मैं स्वयं मांग का अनुमान नहीं लगा सकता - पूर्वानुमान मॉडल से आता है। {name} के लिए योजना {qty} इकाइयाँ ऑर्डर करती है।",
        "ar": "لا أستطيع تقدير الطلب بنفسي - التوقع يأتي من نموذج الطلب. بالنسبة لـ {name}، تطلب الخطة {qty} وحدة.",
    },
}


def _fmt(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if abs(f - round(f)) < 1e-9 else f"{f:g}"


def route_question(question: str) -> str:
    q = (question or "").lower()
    for qtype, kws in _ROUTES:
        if any(kw in q for kw in kws):
            return qtype
    # Urdu "fewer"/"why" may be separated by other words ("کم یونٹ کیوں")
    if "کم" in q and ("کیوں" in q or "کیو" in q):
        return "why_fewer_units"
    return "general"


def _is_estimate_request(question: str) -> bool:
    q = (question or "").lower()
    return any(kw in q for kw in _ESTIMATE_KW)


def _target_item(plan: dict, question: str) -> dict | None:
    items = (plan or {}).get("items", {})
    if not items:
        return None
    q = (question or "").lower()
    for it in items.values():
        if it.get("name", "").lower() in q or it.get("product_id", "").lower() in q:
            return it
    qtokens = set(re.findall(r"[a-z]+", q))
    best, best_score = None, 0
    for it in items.values():
        score = len(qtokens & set(re.findall(r"[a-z]+", it.get("name", "").lower())))
        if score > best_score:
            best, best_score = it, score
    if best is not None:
        return best
    funded = [it for it in items.values() if it.get("order_qty", 0) > 0]
    if funded:
        return max(funded, key=lambda it: it.get("relative_uncertainty", 0.0))
    return next(iter(items.values()))


def _reason_phrase(item: dict, lang: str) -> str:
    codes = item.get("reason_codes") or []
    for c in codes:
        table = _REASON_LOC.get(c)
        if table:
            return table.get(lang) or table.get("en", "")
    return ""


def _derive_facts(plan: dict) -> dict:
    """Local minimal fallback if Member 3's explain_inputs() mock is unavailable."""
    items = (plan or {}).get("items", {})
    funded = [v for v in items.values() if v.get("order_qty", 0) > 0]
    dropped = [v for v in items.values() if v.get("order_qty", 0) <= 0]
    budget = float(plan.get("budget", 0.0)) or 1.0
    return {
        "summary": {
            "budget": plan.get("budget"), "total_spend": plan.get("total_cost"),
            "expected_profit": plan.get("total_expected_profit"),
            "budget_utilization_pct": round(100.0 * plan.get("total_cost", 0.0) / budget, 2),
            "num_products_funded": len(funded), "num_products_dropped": len(dropped),
        },
        "top_allocations": [{"name": it["name"], "qty": it["order_qty"],
                             "spend": it["cost"], "profit": it["expected_profit"], "reason": ""}
                            for it in sorted(funded, key=lambda v: v.get("expected_profit", 0), reverse=True)[:3]],
        "dropped_items": [{"name": it["name"], "cost_to_order": it["unit_cost"],
                           "reason_code": (it.get("reason_codes") or ["DROPPED_LOW_CAPITAL_EFFICIENCY"])[0],
                           "explanation": ""} for it in dropped],
        "uncertainty_alerts": [{"name": it["name"], "relative_uncertainty": it["relative_uncertainty"],
                                "note": "high forecast uncertainty"} for it in items.values()
                               if it.get("uncertainty_flag")],
        "budget_bottleneck": "",
    }


def _template_answer(qtype: str, plan: dict, facts: dict, lang: str, question: str) -> str:
    lang = lang if lang in _T["general"] else "en"
    t = _T[qtype].get(lang) or _T[qtype]["en"]
    s = facts.get("summary", {})

    if qtype == "why_fewer_units":
        it = _target_item(plan, question) or {}
        return t.format(name=it.get("name", ""), qty=_fmt(it.get("order_qty", 0)),
                        reason=_reason_phrase(it, lang),
                        profit=_fmt(it.get("expected_profit", 0)),
                        stockout=_fmt(it.get("expected_stockout_prob", 0)))
    if qtype == "why_excluded":
        dropped = facts.get("dropped_items") or []
        it = dropped[0] if dropped else {}
        plan_item = next((v for v in plan.get("items", {}).values()
                          if v.get("name") == it.get("name")), {})
        return t.format(name=it.get("name", ""), reason=_reason_phrase(plan_item, lang),
                        cost=_fmt(it.get("cost_to_order", 0)))
    if qtype == "what_could_be_wrong":
        alerts = facts.get("uncertainty_alerts") or []
        if not alerts:
            return _T["general"][lang].format(
                budget=_fmt(s.get("budget")), spend=_fmt(s.get("total_spend")),
                profit=_fmt(s.get("expected_profit")), funded=_fmt(s.get("num_products_funded")),
                dropped=_fmt(s.get("num_products_dropped")))
        a = alerts[0]
        return t.format(name=a.get("name", ""), ru=_fmt(a.get("relative_uncertainty", 0)),
                        note=a.get("note", "") if lang == "en" else "")
    if qtype == "what_if_budget":
        sens = plan.get("sensitivity", {})
        b100 = sens.get("100_percent", {})
        b80 = sens.get("80_percent", {})
        return t.format(b100=_fmt(b100.get("budget_amount", s.get("budget"))),
                        p100=_fmt(b100.get("total_expected_profit", s.get("expected_profit"))),
                        b80=_fmt(b80.get("budget_amount", "")),
                        p80=_fmt(b80.get("total_expected_profit", "")))
    return t.format(budget=_fmt(s.get("budget")), spend=_fmt(s.get("total_spend")),
                    profit=_fmt(s.get("expected_profit")),
                    funded=_fmt(s.get("num_products_funded")),
                    dropped=_fmt(s.get("num_products_dropped")))


def _refusal_answer(plan: dict, lang: str, question: str) -> str:
    lang = lang if lang in _T["refuse"] else "en"
    it = _target_item(plan, question) or {}
    return _T["refuse"][lang].format(name=it.get("name", ""), qty=_fmt(it.get("order_qty", 0)))


def _llm_answer(client: LLMClient, question: str, facts: dict, lang: str) -> str:
    body = _PROMPT.format(lang=lang, question=question,
                          facts=json.dumps(facts, ensure_ascii=False, indent=2))
    return client.complete([{"role": "user", "content": body}], temperature=0.0, max_tokens=400)


def explain(
    question: str,
    plan: dict,
    forecasts: dict,
    lang: str,
    *,
    explain_facts: dict | None = None,
    client: LLMClient | None = None,
    offline: bool | None = None,
    settings: Settings | None = None,
) -> Answer:
    s = settings or get_settings()
    plan = plan or {}
    forecasts = forecasts or {}

    if explain_facts is None:
        try:
            from mocks.mock_data import explain_inputs as _ei  # lazy: swap for Member 3
            explain_facts = _ei(plan)
        except Exception:
            explain_facts = _derive_facts(plan)

    sources = {"plan": plan, "explain_inputs": explain_facts, "forecasts": forecasts}
    qtype = route_question(question)
    refused = _is_estimate_request(question)
    use_rules = offline if offline is not None else (s.backend == "mock")

    if refused:
        text = _refusal_answer(plan, lang, question)
        guard_ok = True
    elif use_rules:
        text = _template_answer(qtype, plan, explain_facts, lang, question)
        guard_ok = True
    else:
        try:
            active = client or get_default_client(s)
        except Exception:
            active = None
        text, guard_ok = "", True
        if active is not None:
            try:
                text = _llm_answer(active, question, explain_facts, lang)
                if not check_numbers(text, sources).ok:
                    text = _llm_answer(active, question, explain_facts, lang)  # one retry
            except Exception:
                text = ""
        if not text or not check_numbers(text, sources).ok:
            # reject ungrounded model output -> safe, fully-grounded fallback
            text = _template_answer(qtype, plan, explain_facts, lang, question)
            guard_ok = False

    text = text.strip()
    # Guard on the final, returned text (figures cited must all be grounded).
    guard = check_numbers(text, sources)
    guard_ok = guard_ok and guard.ok

    sources_used = ["plan", "explain_inputs", "forecasts"]
    audit_id = log_event("explain", {
        "model": getattr(client, "name", "RuleBasedTemplate" if use_rules else "LLMClient"),
        "backend": "rule" if use_rules else "amd",
        "language": lang,
        "input_text": question,
        "output": {"text": text, "figures_cited": [f.model_dump() for f in guard.figures],
                   "ungrounded": guard.ungrounded},
        "guard_passed": guard_ok,
        "question_type": qtype,
        "refused": refused,
    }, settings=s)

    return Answer(
        text=text,
        language=lang,
        figures_cited=guard.figures,
        sources_used=sources_used,
        guard_passed=guard_ok,
        refused=refused,
        question_type=qtype,
        audit_id=audit_id,
    )
