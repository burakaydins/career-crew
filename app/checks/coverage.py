"""Every bullet in the new CV must be backed by a claim, so layer 1 cannot be skipped
by simply leaving a bullet out of claims.json."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.checks import Issue
from app.checks.text import normalize

BULLET = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
MATCH_THRESHOLD = 0.85


def bullets(cv: str) -> list[str]:
    return [b.strip() for b in BULLET.findall(cv) if b.strip()]


def is_covered(bullet: str, claims: list[dict]) -> bool:
    b = normalize(bullet)
    for c in claims:
        claim = normalize(str(c.get("claim", "")))
        if claim and (claim == b or SequenceMatcher(None, b, claim).ratio() >= MATCH_THRESHOLD):
            return True
    return False


def check(new_cv: str, claims: list[dict]) -> list[Issue]:
    return [
        Issue("coverage", "error", f"Madde kanıta bağlanmamış (claims.json'da yok): '{b}'")
        for b in bullets(new_cv)
        if not is_covered(b, claims)
    ]
