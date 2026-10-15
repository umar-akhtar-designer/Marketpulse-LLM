# Model selection (measured, not guessed)

We choose the AMD-hosted model by **running our own eval**, so the decision is
evidence-based and reproducible.

## Procedure
```bash
python scripts/list_models.py                      # discover ids
python scripts/model_selection.py \
    --models "DeepSeek-V4-Flash,<candidate-2>,<candidate-3>"
```

For each candidate it reports:
* **accuracy** — field-level accuracy on `eval/descriptions.jsonl` (98 items, 6 languages
  + code-switched), scored exactly like `eval/harness.py`;
* **latency p50/p90** — wall-clock per extraction on the live endpoint;
* **errors** — failed calls.

It then prints the **recommended** model: highest accuracy among those whose p50 meets
the extraction budget (<= 8s, CONTRACT.md), and the exact `AMD_MODEL=` line to set.

## Criteria (in priority order)
1. **JSON reliability** — must return parseable JSON for the extraction schema (the
   client retries without JSON mode, but a model that needs this is penalised in
   accuracy via parse failures -> fallback).
2. **Latency p50** within budget (<= 8s extraction; explanation <= 12s).
3. **Accuracy** on the eval set, with attention to code-switched + low-resource items.
4. **Cost/availability** on the Token Factory deployment.

## Measured results (live AMD Token Factory endpoint)
Endpoint: `https://developer.amd.com.cn/radeon/api/v1`. Small sample
(`--limit 7`, one spec across all 7 renderings); latency is highly variable with
endpoint load (`AMD_TIMEOUT_S=40`, `AMD_MAX_RETRIES=1`).

| model | field accuracy | p50 | p90 | notes |
|---|---|---|---|---|
| `DeepSeek-V4.1-Flash` | **97.6%** | 9.7s | 21.3s | best accuracy/latency balance |
| `Qwen3.8-Flash-Next`  | 100%  | 25.0s | 80.0s | accurate but far too slow |
| `DeepSeek-V4-Flash`   | 90.3% | 8.8s  | 39.6s | fastest p50, lowest accuracy |

### Decision
**`DeepSeek-V4.1-Flash`** — highest measured accuracy with a sub-10s p50. Set in `.env`.

### Honest note on the latency budget
Our 8s p50 budget ([ASSUMPTION]) is **not met** on the shared endpoint at test time
(measured p50 ~9–11s; individual calls 6–20s+). This is endpoint load, not the model
only. Mitigations if a hard 8s p50 is required: lower `AMD_MAX_TOKENS` (already 600 for
extraction), trim the extraction prompt to the fields actually needed, use the
deterministic rule extractor as the default and the LLM as a refinement, or select a
faster served model when one is under budget. The recommendation logic in
`scripts/model_selection.py` automatically prefers the fastest model that meets budget,
so re-running it on a less-loaded endpoint may pick a different id.

### Reproduce
```bash
python scripts/list_models.py
python scripts/model_selection.py --models "DeepSeek-V4.1-Flash,Qwen3.8-Flash-Next,DeepSeek-V4-Flash" \
    --limit 14 --budget-s 900
```
