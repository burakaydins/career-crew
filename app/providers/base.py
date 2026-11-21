"""Provider interface. Every provider returns the same JSON envelope:

    {"message": str, "data": dict, "files": {name: content}}

Inputs are passed inline in the prompt and files are written by the
orchestrator, so agents need no tool access in any mode.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.registry import AgentCard


@dataclass
class AgentRequest:
    card: AgentCard
    skill: str
    system_prompt: str
    user_prompt: str
    workdir: Path
    iteration: int = 1


@dataclass
class AgentResult:
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str

    def run(self, request: AgentRequest) -> AgentResult: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_envelope(text: str) -> AgentResult:
    """Extract the JSON envelope from a model reply, tolerating code fences or stray prose."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError(f"Yanıtta JSON bulunamadı: {text[:200]!r}")
    try:
        obj = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ProviderError(f"Yanıt JSON olarak okunamadı: {e}") from e
    if not isinstance(obj, dict):
        raise ProviderError("Yanıt bir JSON nesnesi olmalı")
    data = obj.get("data") or {}
    if not isinstance(data, dict):
        raise ProviderError("'data' alanı bir nesne olmalı")
    files = obj.get("files") or {}
    if not isinstance(files, dict):
        raise ProviderError("'files' alanı bir nesne olmalı")
    return AgentResult(
        message=str(obj.get("message", "")).strip(),
        data=data,
        files={str(k): str(v) for k, v in files.items()},
    )
