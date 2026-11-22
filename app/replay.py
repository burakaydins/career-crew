"""Replays a finished run from its events.jsonl, through the same Renderer (terminal) or the same
event stream (web) that showed it live."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator

from app.events import Event

MAX_GAP = 1.5  # seconds: long waits (a model thinking, a user reading the job gate) are cut to this
MIN_GAP = 0.15


class ReplayError(RuntimeError):
    """The run folder has no usable events.jsonl."""


def load_events(run_dir: Path) -> list[Event]:
    path = run_dir / "events.jsonl"
    if not run_dir.is_dir():
        raise ReplayError(f"Klasör bulunamadı: {run_dir}")
    if not path.is_file():
        raise ReplayError(f"events.jsonl yok: {path}. Bu klasör bir çalıştırma kaydı değil.")
    events: list[Event] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            events.append(Event(type=str(raw["type"]), agent=raw.get("agent"), data=dict(raw.get("data") or {}),
                                ts=float(raw["ts"])))
        except (ValueError, KeyError, TypeError) as e:
            raise ReplayError(f"events.jsonl bozuk (satır {n}): {type(e).__name__} {e}") from e
    if not events:
        raise ReplayError(f"events.jsonl boş: {path}")
    return events


def delays(events: Iterable[Event], speed: float = 1.0) -> list[float]:
    """Seconds to wait before each event. Real gaps are scaled by `speed`, then long ones are shortened."""
    out: list[float] = []
    prev: float | None = None
    for e in events:
        gap = 0.0 if prev is None else max(0.0, e.ts - prev)
        prev = e.ts
        out.append(0.0 if not out else min(max(gap / speed, MIN_GAP / speed), MAX_GAP / speed))
    return out


def play(events: list[Event], emit: Callable[[Event], None], speed: float = 1.0, instant: bool = False,
         sleep: Callable[[float], None] = time.sleep) -> Iterator[Event]:
    """Calls emit() for every event, waiting as the original run did unless `instant`."""
    for event, wait in zip(events, delays(events, speed)):
        if not instant and wait:
            sleep(wait)
        emit(event)
        yield event


def run_language(run_dir: Path) -> str:
    """The prompt language the run used (agent names do not change, but the registry needs one)."""
    try:
        from app import persist
        return persist.read(run_dir)["state"].get("lang") or "tr"
    except Exception:
        return "tr"
