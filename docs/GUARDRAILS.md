# Guardrails — "the LLM never forecasts or computes"

The single non-negotiable rule of this layer: **every number a retailer sees must
originate from another member's module** (Member 2 forecasts / Member 3 optimizer).
The LLM may only *translate and explain*. This is enforced in code, not just by prompt.

## 1. Number guard (`llm/guard.py`)
`check_numbers(text, sources)` scans the answer for numeric tokens and verifies each one
traces to a value in `plan` + `explain_inputs(plan)` + `forecasts` — including numbers
embedded inside reason strings.

* Match rule: exact after rounding to 2 dp, **or** `|diff| <= 0.01`; a `%` token also
  matches `value/100` (so `12%` grounds against `0.12`).
* Anything ungrounded is collected in `GuardResult.ungrounded` and the result is `ok=False`.
* Arabic-Indic / Devanagari digits are normalised to ASCII first.

## 2. Reject-and-fallback (`llm/explainer.py`)
On the live path the model's answer is guarded. If it contains any ungrounded number
(even after one retry), the output is **rejected** and a deterministic, fully-grounded
template answer is returned instead; the returned `Answer.guard_passed` is `False` so the
caller (and the audit log) can see the model was overruled.

## 3. Refusal of estimate requests
Questions containing estimate/predict intent ("just estimate", "predict", "roughly",
"اندازہ", "قدّر", "अनुमान", ...) are detected and answered with a refusal that redirects
to the models (`Answer.refused = True`). The assistant never produces a forecast number.

## 4. Extraction never guesses (`llm/extraction.py`, `llm/schemas.py`)
* LLM-extracted values are validated against controlled vocabularies; invalid values are
  nulled (never silently kept).
* Any field that is missing/low-confidence (< `LLM_CONFIDENCE_THRESHOLD`, default 0.6)
  raises a **follow-up question** in the retailer's language; `needs_confirmation=True`.
* `apply_corrections()` sets human-confirmed fields to confidence `1.0` and clears their
  follow-ups.

## 5. Audit trail (`llm/audit.py`)
Every extraction/explanation/correction appends a JSONL record: model, backend,
language, input, output, guard result, question type, timestamp. Append-only, secret-free,
and failures to write never break the request path.

## What the guard is *not*
It does not judge factual correctness of the optimizer/forecast inputs (that is Members
2/3). It guarantees the LLM **introduces nothing new** — no fabricated quantities, costs,
profits, or forecasts.
