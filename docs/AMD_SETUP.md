# AMD setup (live endpoint)

MarketPulse AI uses an **AMD-hosted, OpenAI-compatible** endpoint (Token Factory).
The code talks to it through the `openai` Python SDK, so any OpenAI-compatible
served model works by changing two values.

## 1. Get your endpoint details
In the AMD Token Factory console open the model's **detail dialog**. You need:

| value | env var | example |
|---|---|---|
| Base URL | `AMD_BASE_URL` | `https://developer.amd.com.cn/radeon/api/v1` |
| API key  | `AMD_API_KEY`  | `rc-...` |
| Model id | `AMD_MODEL`    | the exact id shown in the dialog |

> `AMD_BASE_URL` and `AMD_MODEL` must be copied **exactly** from the console — they
> differ per deployment. Do not guess them.

## 2. Configure `.env`
```bash
cp .env.example .env
# edit .env:
#   MARKETPULSE_LLM_BACKEND=amd
#   AMD_BASE_URL=...
#   AMD_API_KEY=rc-...
#   AMD_MODEL=...
```
`.env` is **gitignored** and must never be committed. No secret is hardcoded anywhere.

## 3. Verify connectivity
```bash
python scripts/list_models.py
```
Prints the ids the endpoint exposes — use one of these for `AMD_MODEL`.

## 4. Run the live demos
```bash
python demo/demo_end_to_end.py --live      # extraction + grounded assistant
python eval/harness.py --live              # accuracy against the eval set
python scripts/measure_latency.py          # p50/p90 vs the 8s/12s budget
```

## 5. Backends
`MARKETPULSE_LLM_BACKEND` selects the path:

* `mock` (default) — deterministic rule extractor + templates. **No network.** Used by
  the whole test suite and CI so results are reproducible and the shared key is not
  hammered.
* `amd` — live `AMDClient`. Falls back to the rule extractor if the network/JSON fails,
  so a request never crashes (see `llm/extraction.py`).

## Notes / gotchas
* `temperature=0.0` by default for reproducibility.
* Some served models reject `response_format={"type":"json_object"}`; `AMDClient`
  automatically retries the request without JSON mode.
* Timeouts/retries are configurable: `AMD_TIMEOUT_S`, `AMD_MAX_RETRIES`.
