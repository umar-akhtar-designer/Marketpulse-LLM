"""LLM clients.

- ``LLMClient``   : the protocol everything depends on.
- ``AMDClient``   : live, OpenAI-compatible AMD Token Factory endpoint.
- ``MockLLMClient``: deterministic, offline, no network.

The same code path handles extraction and explanation; tests swap in ``MockLLMClient``
so results are reproducible and the shared API key is not hammered.
"""

from __future__ import annotations

import time
from typing import Callable, Protocol

from .config import Settings, get_settings


class LLMClient(Protocol):
    name: str
    backend: str

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str: ...


class MockLLMClient:
    """Offline deterministic client.

    ``responder`` may be:
      * a str  -> always returned;
      * a ``callable(messages) -> str``;
      * a list[str] -> popped in order (last one repeats).
    """

    backend = "mock"

    def __init__(self, responder="", name: str = "MockLLMClient"):
        self._responder = responder
        self._queue: list[str] = list(responder) if isinstance(responder, list) else []
        self.name = name
        self.calls: list[list[dict]] = []

    def complete(self, messages, *, temperature=None, max_tokens=None, json_mode=False) -> str:
        self.calls.append(messages)
        r = self._responder
        if callable(r):
            return r(messages)
        if self._queue:
            return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return r if isinstance(r, str) else ""


class AMDClient:
    """Live client for an OpenAI-compatible endpoint (AMD Token Factory / vLLM)."""

    backend = "amd"

    def __init__(self, settings: Settings | None = None, model: str | None = None):
        from openai import OpenAI  # imported lazily so tests need no network

        self.settings = settings or get_settings()
        self.model = model or self.settings.model
        self.name = f"AMDClient:{self.model}"
        self._client = OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            timeout=self.settings.timeout_s,
            max_retries=self.settings.max_retries,
        )
        self.last_latency_ms: float | None = None

    def complete(self, messages, *, temperature=None, max_tokens=None, json_mode=False) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception:
            if json_mode:  # some served models reject json mode; retry plainly
                kwargs.pop("response_format", None)
                resp = self._client.chat.completions.create(**kwargs)
            else:
                raise
        finally:
            self.last_latency_ms = (time.perf_counter() - start) * 1000.0
        return resp.choices[0].message.content or ""


def get_default_client(settings: Settings | None = None) -> LLMClient:
    s = settings or get_settings()
    if s.backend == "amd" and s.has_live_credentials:
        return AMDClient(s)
    return MockLLMClient()
