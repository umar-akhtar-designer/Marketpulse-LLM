# MarketPulse AI — Member 4: LLM Layer

Multilingual **shop-description extraction** + a **grounded AI Decision Assistant**
(Component E) for MarketPulse AI (AMD Developer Hackathon, ACT III).

> **Core principle:** the LLM only *translates and explains*. It **never forecasts or
> computes money** — every number comes from Member 2 (forecasts) or Member 3
> (optimizer). This is enforced by code, not just prompts. See `docs/GUARDRAILS.md`.

## What's in the box
* `extract_profile(text) -> Profile` — free-form description (any of 6 languages, incl.
  code-switched) → a language-neutral, schema-valid profile, or **follow-up questions**
  for anything not stated (never a guess).
* `apply_corrections(profile, edits) -> Profile` — retailer confirm/correct → confidence `1.0`.
* `explain(question, plan, forecasts, lang) -> Answer` — grounded answers in 6 languages,
  with a **number guard** that rejects any invented figure and falls back to a safe,
  fully-grounded reply.
* A live **AMD (OpenAI-compatible)** client + a deterministic offline client, a JSONL
  **audit log**, and a reproducible **eval harness** with model selection.

## Install
```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Targets Python 3.10+ (developed on 3.14).

## Run the tests (no network)
```bash
pytest            # 114 tests: normalizers, schemas, guard, gazetteer, extraction,
                  # explainer, offline latency, and the eval-based accuracy gate
```

## Evaluate extraction (no network)
```bash
python eval/build_eval.py     # regenerate eval/descriptions.jsonl (98 items, deterministic)
python eval/harness.py        # -> eval/out/report.{json,md}
```
Reports schema validity, per-field/per-language accuracy (core vs low-resource),
confidence calibration, and cross-language consistency. The same harness is asserted in
`tests/test_extraction_accuracy.py`.

## Demo (no network)
```bash
python demo/demo_end_to_end.py
```
Shows multilingual extraction → follow-ups → corrections → grounded answers →
adversarial refusal, end to end.

## Live AMD endpoint
```bash
cp .env.example .env      # fill AMD_BASE_URL / AMD_API_KEY / AMD_MODEL (never commit)
python scripts/list_models.py                 # discover the exact model id
python scripts/model_selection.py --models "id1,id2"   # pick by accuracy + latency
python demo/demo_end_to_end.py --live
python scripts/measure_latency.py             # p50/p90 vs the 8s/12s budget
```
Full guide: `docs/AMD_SETUP.md`, model choice: `docs/MODEL_SELECTION.md`.

## Repository layout
```
llm/            the layer (schemas, clients, normalizers, gazetteer, extraction, guard, explainer, audit)
  prompts/      extraction.txt, explain.txt
  data/         gazetteer_karachi.json
mocks/          Member 2/3 outputs (forecasts, plan, explain_inputs) — clearly separated
eval/           build_eval.py, harness.py, descriptions.jsonl, out/ (git-ignored)
scripts/        list_models.py, model_selection.py, measure_latency.py
demo/           demo_end_to_end.py
docs/           AMD_SETUP, MODEL_SELECTION, GUARDRAILS, PROMPTS, LANGUAGE_SCOPE
tests/          pytest suite
CONTRACT.md     exact schemas/signatures + labeled [ASSUMPTION]s for the team
```

## Contracts & integration
`CONTRACT.md` is the source of truth for the `Profile`/`Answer` shapes, controlled
vocabularies, function signatures, the latency budget, and every `[ASSUMPTION]`.
Teammate modules drop in behind the same signatures used by `mocks/mock_data.py`
(replace `mocks` with Member 2/3's real `forecasts` / `plan` / `explain_inputs`).
