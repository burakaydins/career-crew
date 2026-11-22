"""Loads Agent Cards from app/agents/*.json and their prompt files (app/prompts/<lang>/)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Agent cards and prompts live inside the package so a normal (non-editable) install ships them.
ROOT = Path(__file__).resolve().parent
LANGUAGES = ("tr", "en")
DEFAULT_LANG = "tr"


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

    def system_prompt(self, root: Path = ROOT, lang: str = DEFAULT_LANG) -> str:
        # promptFile names the default (Turkish) prompt; other languages use the same file name.
        folder = root / "prompts" / lang
        role = (folder / Path(self.promptFile).name).read_text(encoding="utf-8").strip()
        contract = (folder / "_contract.md").read_text(encoding="utf-8").strip()
        return f"{role}\n\n{contract}\n"


class Registry:
    def __init__(self, root: Path = ROOT, lang: str = DEFAULT_LANG) -> None:
        if lang not in LANGUAGES:
            raise ValueError(f"Desteklenmeyen dil: {lang} (desteklenenler: {', '.join(LANGUAGES)})")
        self.root = root
        self.lang = lang
        self.cards: dict[str, AgentCard] = {}
        for path in sorted((root / "agents").glob("*.json")):
            card = AgentCard(**json.loads(path.read_text(encoding="utf-8")))
            self.cards[card.name] = card
        if not self.cards or not (root / "prompts" / lang / "_contract.md").is_file():
            raise FileNotFoundError(
                f"Ajan kartları ya da promptlar bulunamadı ({root / 'agents'}, {root / 'prompts' / lang}). "
                "Kurulum eksik: projeyi 'pip install -e .' ile ya da tam bir paketten kurun."
            )

    def __getitem__(self, name: str) -> AgentCard:
        return self.cards[name]

    def __contains__(self, name: str) -> bool:
        return name in self.cards
