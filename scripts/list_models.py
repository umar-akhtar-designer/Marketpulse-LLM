"""List the model ids exposed by the configured OpenAI-compatible endpoint.

Use this to discover the EXACT model id to put in AMD_MODEL.

    python scripts/list_models.py

Requires AMD_BASE_URL + AMD_API_KEY in the environment (or a local .env).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    print(f"base_url : {s.base_url}")
    print(f"backend  : {s.backend}")
    print(f"env model: {s.model}")
    if not s.has_live_credentials:
        print("\n[!] No live credentials found. Set AMD_API_KEY (and AMD_BASE_URL) "
              "in .env or the environment.")
        return 2
    try:
        from openai import OpenAI
        client = OpenAI(base_url=s.base_url, api_key=s.api_key, timeout=s.timeout_s,
                        max_retries=s.max_retries)
        models = client.models.list().data
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"\n[!] Could not list models: {exc}")
        return 1
    print("\nAvailable models:")
    for m in sorted(models, key=lambda x: getattr(x, "id", "")):
        print(f"  - {m.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
