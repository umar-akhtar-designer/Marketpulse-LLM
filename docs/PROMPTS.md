# Prompts

Two prompts live in `llm/prompts/`. They are loaded once at import; the runtime values
(field spec / facts) are injected per call.

## `extraction.txt`
Role: an **information-extraction engine** that copies stated facts only — explicitly
forbidden to forecast, estimate, or compute.

* Returns **one JSON object** conforming to the schema; no prose, no markdown fences.
* Every field is `{"value": ..., "confidence": 0.0-1.0}`; uncertain/missing -> `null`
  with low confidence (never invented).
* Lists the allowed values for every controlled vocabulary inline (`{field_spec}`).
* Normalisation hints ("30k" -> 30000; payday = day-of-month ints / "last").
* Includes a `{locale}` hint and the raw `{text}`.

Parsing is defensive (`llm/extraction.py::_llm_extract`): strips code fences, tries
`json.loads`, then a regex extract of the first `{...}` block, and accepts either
`{"field": {...}}` or `{"fields": {...}}`. Any failure -> deterministic rule extractor.

## `explain.txt`
Role: the **Decision Assistant** that explains a plan; explicitly forbidden to forecast
or calculate.

ABSOLUTE RULES in the prompt:
1. every number must appear verbatim in the FACTS block — never invent/round/compute;
2. refuse "just estimate"/predict requests and point to the demand model;
3. reply in the requested `{lang}`;
4. concise (<= 120 words), cite product names as given.

The prompt is backed by **code**, not trust: the FACTS block is `explain_inputs(plan)`,
and the returned text is passed through the number guard (see `docs/GUARDRAILS.md`).
Ungrounded output is discarded and replaced by a grounded template.

## Why prompts are not the only defence
Prompts can be ignored. The guard + reject-and-fallback + schema validation mean a
misbehaving or jailbroken model can never leak an invented figure to the retailer.
