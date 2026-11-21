"""Task model adapted from A2A: Task, Message, Part, Artifact."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    INPUT_REQUIRED = "input-required"


@dataclass
class TextPart:
    text: str
    kind: str = "text"


@dataclass
class FilePart:
    path: str
    mime: str = "text/markdown"
    kind: str = "file"


@dataclass
class DataPart:
    data: dict[str, Any]
    kind: str = "data"


Part = TextPart | FilePart | DataPart


@dataclass
class Message:
    sender: str
    parts: list[Part] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(p.text for p in self.parts if isinstance(p, TextPart))


@dataclass
class Artifact:
    name: str
    path: str


@dataclass
class Task:
    agent: str
    skill: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    state: TaskState = TaskState.SUBMITTED
    messages: list[Message] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    error: str | None = None
