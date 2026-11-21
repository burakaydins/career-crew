"""In-process event bus. Every event is also appended to events.jsonl for replay."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Event:
    type: str
    agent: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, fn: Subscriber) -> None:
        self._subscribers.append(fn)

    def publish(self, type: str, agent: str | None = None, **data: Any) -> Event:
        event = Event(type=type, agent=agent, data=data)
        # Parallel steps publish from worker threads; keep output ordered.
        with self._lock:
            for fn in self._subscribers:
                fn(event)
        return event


class JsonlSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __call__(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
