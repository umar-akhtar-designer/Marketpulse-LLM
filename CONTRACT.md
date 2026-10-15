# Shared Contract — Member 4 (LLM Layer: Extraction + AI Decision Assistant)

This document defines the exact input/output schemas, function signatures, and JSON
payloads for **Member 4's workstream** in MarketPulse AI.

- **Owner / Author:** Member 4 (LLM Layer, Multilingual Extraction, Component E)
- **Consumers:** Member 5 (API & interface)
- **Providers (inputs consumed):** Member 3 (`Plan`, `explain_inputs()`),
  Member 2 (forecasts), Member 1 (location / store data)

> **CORE PRINCIPLE.** The LLM only translates and explains. It never forecasts and
> never performs financial arithmetic. Every number produced by this module must
> originate from Member 2 (forecasts) or Member 3 (optimizer) output.
>
> **ASSUMPTION POLICY.** Every value below that was not fixed by an upstream contract
> is marked **[ASSUMPTION]**. Assumptions are explicit and may be revised by the team;
> the code never silently picks constants.

---

## 1. Public Entry-Point Signatures

```python
# llm/extraction.py
def extract_profile(text: str, *, locale: str | None = None,
                    threshold: float | None = None) -> Profile: ...

def apply_corrections(profile: Profile, edits: dict) -> Profile: ...

# llm/explainer.py
def explain(question: str, plan: Plan, forecasts: dict[str, Forecast],
            lang: str, *, explain_facts: dict | None = None) -> Answer: ...

# llm/normalizers.py
def normalize_money(text: str, locale: str) -> Money | None: ...
def normalize_quantity(text: str, locale: str) -> float | None: ...
def normalize_date(text: str, locale: str, today: date | None = None) -> DateResult | None: ...

# llm/gazetteer.py
def resolve_place(name: str, region: str = "south_asia_karachi") -> PlaceMatch: ...
```

`Plan` and `Forecast` are **provided by other members** (see §5, §6). We do not redefine them.
We only define `Profile`, `Answer`, and the small helper value objects below.

---

## 2. Extraction Output: `Profile`

Language-neutral. One schema for every supported language.

### 2.1 Shape

```json
{
  "fields": {
    "location_type":   {"value": "urban_flagship", "confidence": 0.82},
    "income_band":     {"value": "medium",         "confidence": 0.55},
    "payday":          {"value": [25, 30],         "confidence": 0.60},
    "nearby_anchors":  {"value": ["school", "market"], "confidence": 0.71},
    "shop_category":   {"value": "grocery",        "confidence": 0.93},
    "currency":        {"value": "PKR",            "confidence": 0.95},
    "budget":          {"value": 5000.0,           "confidence": 0.90},
    "language_detected": {"value": "ur",           "confidence": 0.97}
  },
  "follow_up_questions": [
    {"field": "income_band",
     "question": "Would you describe your neighborhood as low, medium, or high income?",
     "reason": "low_confidence"}
  ],
  "needs_confirmation": true,
  "locale": "en-PK",
  "source_language": "ur",
  "text": "near Liaquatabad market, mostly grocery, budget 5000 rupees, payday 25 aur 30",
  "audit_id": "b1f2c3d4e5f6",
  "model": "MockLLMClient",
  "created_at": "2026-10-15T10:00:00Z"
}
```

### 2.2 Field value objects

All 8 fields use the identical `{value, confidence}` envelope.

| Field | `value` type | Allowed values / format | Notes |
|---|---|---|---|
| `location_type` | `str` | `urban_flagship` \| `suburban_medium` \| `rural_kiosk` | **[ASSUMPTION]** Reuses Member 1's `stores_df.location_type` enum so the profile maps directly onto their schema. Descriptive phrases ("near a market") go to `nearby_anchors`. |
| `income_band` | `str` | `low` \| `medium` \| `high` | **[ASSUMPTION]** Team may extend (e.g. `lower_middle`). |
| `payday` | `list[int]` | day-of-month `1..31`, and/or the token `"last"` | **[ASSUMPTION]** `[25, 30]` = 25th and 30th; `["last"]` = last day of month. |
| `nearby_anchors` | `list[str]` | controlled vocab (below) | **[ASSUMPTION]** Ordered by relevance, de-duplicated. |
| `shop_category` | `str` | controlled vocab (below) | **[ASSUMPTION]** |
| `currency` | `str` | ISO-4217, uppercase (e.g. `PKR`, `USD`, `EUR`) | |
| `budget` | `float` | `>= 0`, normalized to `currency` | Normalizers convert "30k" → `30000.0`. |
| `language_detected` | `str` | ISO-639-1: `en`,`ur`,`es`,`sw`,`hi`,`ar` | For code-switched text, report the **dominant** language. |

**Controlled vocabulary — `nearby_anchors` [ASSUMPTION]:**
`school, university, market, mosque, church, temple, hospital, clinic, mall,
bus_station, railway_station, factory, office, residential_area, park, stadium`

**Controlled vocabulary — `shop_category` [ASSUMPTION]:**
`grocery, pharmacy, clothing, electronics, hardware, restaurant, cosmetics,
stationery, general_store, bakery, mobile_accessories`

### 2.3 Confidence & follow-up

- `confidence` is a float in `[0.0, 1.0]`.
- **[ASSUMPTION]** Default threshold = `0.6` (env `LLM_CONFIDENCE_THRESHOLD`).
  Any field with `confidence < threshold`:
  1. is **not** treated as a guess,
  2. produces one entry in `follow_up_questions`, and
  3. sets `needs_confirmation = true`.
- A field that cannot be resolved at all gets `value: null, confidence: 0.0` and a
  follow-up question (`reason: "missing"`).

### 2.4 Retailer confirm / correct

```python
def apply_corrections(profile: Profile, edits: dict) -> Profile
```

`edits` is a partial map `field -> value` (or `field -> {"value": ...}`). Returns a new
`Profile` where edited fields are set to the edited value with `confidence = 1.0`
(**[ASSUMPTION]**: a human-confirmed value is maximally confident), their follow-up
questions are removed, `needs_confirmation` is recomputed, and the change is written to
the audit log (`action: "correction"`).

```json
// example edits
{"income_band": "low", "budget": 4200, "payday": [1]}
```

---

## 3. Explanation Output: `Answer` (Component E)

```json
{
  "text": "آپ نے چاول کے 48 پیکٹ منگوائے ہیں کیونکہ اس پر منافع زیادہ ہے۔",
  "language": "ur",
  "figures_cited": [
    {"value": 48, "source_path": "plan.items.SKU_RICE_5KG.order_qty",
     "label": "Basmati Rice 5kg", "display": "48"}
  ],
  "sources_used": ["plan", "explain_inputs", "forecasts"],
  "guard_passed": true,
  "refused": false,
  "question_type": "why_fewer_units",
  "audit_id": "9a8b7c6d5e4f"
}
```

| Key | Type | Description |
|---|---|---|
| `text` | `str` | Reply in `lang`. Contains only figures present in the source data. |
| `language` | `str` | ISO-639-1 of the reply (echoes `lang`). |
| `figures_cited` | `list[FigureRef]` | Every number appearing in `text`, with the exact source path it came from. |
| `sources_used` | `list[str]` | Subset of `["plan","explain_inputs","forecasts"]`. |
| `guard_passed` | `bool` | `true` iff the number guard found **no** ungrounded figure. |
| `refused` | `bool` | `true` if the request asked the model to forecast/invent a number and the router redirected/refused. |
| `question_type` | `str` | `why_fewer_units` \| `what_if_budget` \| `what_could_be_wrong` \| `why_excluded` \| `general` |
| `audit_id` | `str` | Joins to the audit log entry. |

### 3.1 Question routing [ASSUMPTION]

| `question_type` | Trigger (keywords, per language) | Retrieval source |
|---|---|---|
| `why_fewer_units` | "why fewer", "why so few", "kam kyun" | `plan.items[*]` + `explain_inputs.top_allocations` |
| `what_if_budget` | "what if", "if budget", "budget changes" | `plan.sensitivity` |
| `what_could_be_wrong` | "what could go wrong", "risk", "uncertain" | `explain_inputs.uncertainty_alerts` |
| `why_excluded` | "why not", "excluded", "left out", "dropped" | `explain_inputs.dropped_items` |
| `general` | none of the above | summary of `explain_inputs.summary` |

### 3.2 Number guard [ASSUMPTION]

1. Extract every numeric token from `text` (integers, decimals, percentages, and
   numbers with thousands separators, incl. non-Latin digits).
2. Build the set of **grounded numbers** from `plan`, `explain_inputs(plan)`, and
   `forecasts` (recursively). Grounded numbers include values *and* simple derived
   figures the optimizer already returned (costs, profits, budgets, p10/p50/p90, etc.).
3. A cited number passes if it matches a grounded number within the tolerance rules
   (`round-to-nearest-int` for %/pct, exact for currency, ±1 float epsilon).
4. If any figure is ungrounded: **regenerate once** with a stricter prompt. If it still
   fails, return a deterministic **template fallback** built only from grounded values,
   with `guard_passed = false`.
5. The guard is tested by injecting a fake figure into model output and confirming
   detection (target: 100% catch on the adversarial set).

### 3.3 "Just estimate" refusal [ASSUMPTION]

If the question asks the model to forecast or invent a number (e.g. "just estimate how
many I'll sell", "roughly what profit"), the module does **not** comply. It returns
`refused = true` and a redirect such as: *"I can't estimate demand myself — the forecast
comes from the demand model. Here is the model's number: …"*, citing the real value.

---

## 4. Helper value objects

```json
// Money (llm/normalizers.py)
{"amount": 5000.0, "currency": "PKR", "raw": "5,000", "locale": "en-PK"}

// DateResult
{"iso": "2026-10-25", "kind": "explicit_day", "raw": "the 25th", "locale": "en-PK"}
// kind: explicit_day | end_of_month | next_month_start | relative | parsed

// PlaceMatch (llm/gazetteer.py)
{"matched": true, "matched_name": "Liaquatabad Market",
 "location_type": "urban_flagship", "confidence": 0.8, "region": "south_asia_karachi",
 "kind": "market"}
```

---

## 5. Input consumed from Member 2 — `Forecast`

(Reproduced from Member 3's `CONTRACT.md`; source of truth is Member 2.)

```json
{"p10": 12.0, "p50": 30.0, "p90": 58.0, "mean": 32.5, "std": 14.2, "horizon_days": 14}
```

## 6. Input consumed from Member 3 — `Plan` and `explain_inputs()`

Source of truth: Member 3's repository `CONTRACT.md`. Key `Plan` keys we consume:
`budget, total_cost, total_expected_profit, total_items_ordered, binding_constraints,
items{product_id -> {...order_qty, cost, unit_cost, unit_price, expected_profit,
expected_stockout_prob, critical_ratio, binding_constraints, reason_codes,
uncertainty_flag, relative_uncertainty}}, sensitivity{...}`.

`explain_inputs(plan)` returns: `summary, top_allocations, dropped_items,
uncertainty_alerts, budget_bottleneck`.

Members 2 and 3 are **mocked** in `mocks/` (clearly separated) and swapped for the real
modules at integration time. Mocks follow these contracts exactly.

## 7. Inputs consumed from Member 1 — location data

`location_type` enum and `region_id` keys come from Member 1's `stores_df` contract
(`urban_flagship | suburban_medium | rural_kiosk`; e.g. `south_asia`, `ecuador`). The
Karachi gazetteer maps place names onto this enum via `resolve_place()`.

---

## 8. Audit log record [ASSUMPTION]

Append-only JSONL, one object per call.

```json
{
  "audit_id": "b1f2c3d4e5f6",
  "ts": "2026-10-15T10:00:00Z",
  "action": "extract",
  "model": "MockLLMClient",
  "backend": "mock",
  "language": "ur",
  "input_text": "...",
  "output": {"...": "extracted fields or answer text"},
  "guard_passed": null,
  "corrections": null,
  "latency_ms": 12,
  "prompt_sha256": "…"
}
```

`action` ∈ `extract | explain | correction | followup`.

---

## 9. Supported languages (this release) [ASSUMPTION]

`en`, `ur`, `es`, `sw`, `hi`, `ar` — plus **code-switched** input mixing any of these
with English. Low-resource languages/dialects are **out of scope** for this release and
are named explicitly in `docs/LANGUAGE_SCOPE.md`. Confidence is expected to be lower for
`sw`/`hi`/`ar` than `en`/`es`/`ur`; the extraction accuracy report breaks results down
per language.

---

## 10. Change log

| Date | Change | Author |
|---|---|---|
| 2026-10-15 | Initial contract; all `[ASSUMPTION]` items confirmed with project owner. | Member 4 |
