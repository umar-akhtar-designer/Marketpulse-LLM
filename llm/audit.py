"""Append-only audit log (JSONL).

Records what was said, what was extracted, and what changed - guardrail F in the task
file. Never stores secrets. Failures to write are swallowed so they cannot break the
request path, but are surfaced to stderr.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, get_settings


def new_audit_id() -> str:
    return uuid.uuid4().hex[:12]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_event(action: str, payload: dict, audit_id: str | None = None,
              settings: Settings | None = None) -> str:
    s = settings or get_settings()
    audit_id = audit_id or new_audit_id()
    record = {
        "audit_id": audit_id,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        **payload,
    }
    try:
        path = Path(s.audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # pragma: no cover - defensive
        print(f"[audit] could not write audit log: {exc}", file=sys.stderr)
    return audit_id
