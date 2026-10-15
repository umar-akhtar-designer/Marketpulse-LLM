"""Pytest bootstrap: make ``llm``/``mocks`` importable and keep tests hermetic.

Audit writes go to a temp file (not the repo) and the backend is forced to the
deterministic mock path so the suite never touches the network.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MARKETPULSE_LLM_BACKEND", "mock")
os.environ.setdefault("LLM_AUDIT_PATH",
                      str(Path(tempfile.gettempdir()) / "marketpulse_test_audit.jsonl"))
