"""Loads Agent Cards from agents/*.json and their prompt files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_FILE = "prompts/tr/_contract.md"


@dataclass
class AgentCard:
    name: str
    displayName: str
    description: str
    skills: list[str]
    model: str
    effort: str
    color: str
    promptFile: str
    allowedTools: list[str] = field(default_factory=list)

    def system_prompt(self, root: Path = ROOT) -> str:
        role = (root / self.promptFile).read_text(encoding="utf-8").strip()
        contract = (root / CONTRACT_FILE).read_text(encoding="utf-8").strip()
        return f"{role}\n\n{contract}\n"


class Registry:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.cards: dict[str, AgentCard] = {}
        for path in sorted((root / "agents").glob("*.json")):
            card = AgentCard(**json.loads(path.read_text(encoding="utf-8")))
            self.cards[card.name] = card

    def __getitem__(self, name: str) -> AgentCard:
        return self.cards[name]

    def __contains__(self, name: str) -> bool:
        return name in self.cards
