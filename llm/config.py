"""Environment-driven configuration. No secrets are hardcoded.

All values come from environment variables (optionally loaded from a local .env file,
which is gitignored). See .env.example.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: str | os.PathLike | None = None) -> None:
    """Minimal .env loader (no external dependency). Existing env vars win."""
    env_path = Path(path) if path else (_REPO_ROOT / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    # --- LLM backend ---
    backend: str          # "amd" | "mock"
    base_url: str
    api_key: str
    model: str
    timeout_s: float
    max_retries: int
    temperature: float

    # --- extraction behaviour ---
    confidence_threshold: float

    # --- audit ---
    audit_path: str

    @property
    def has_live_credentials(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("rc-REPLACE")


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        backend=os.environ.get("MARKETPULSE_LLM_BACKEND", "mock").strip().lower(),
        base_url=os.environ.get("AMD_BASE_URL", "https://developer.amd.com.cn/radeon/api/v1").strip(),
        api_key=os.environ.get("AMD_API_KEY", "").strip(),
        model=os.environ.get("AMD_MODEL", "DeepSeek-V4.1-Flash").strip(),
        timeout_s=float(os.environ.get("AMD_TIMEOUT_S", "60")),
        max_retries=int(os.environ.get("AMD_MAX_RETRIES", "3")),
        temperature=float(os.environ.get("AMD_TEMPERATURE", "0.0")),
        confidence_threshold=float(os.environ.get("LLM_CONFIDENCE_THRESHOLD", "0.6")),
        audit_path=os.environ.get("LLM_AUDIT_PATH", str(_REPO_ROOT / "llm" / "audit" / "audit.jsonl")),
    )
