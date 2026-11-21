"""Title and seniority inflation, e.g. "Junior Developer" -> "Senior Developer"."""

from __future__ import annotations

import re

from app.checks import Issue
from app.checks.text import normalize

SENIORITY = [
    "senior", "sr", "lead", "principal", "staff", "head", "chief", "director", "manager",
    "kidemli", "lider", "takim lideri", "yonetici", "mudur", "direktor", "sef", "basmuhendis",
]


def count(text: str, word: str) -> int:
    return len(re.findall(rf"(?<![0-9a-z]){re.escape(word)}(?![0-9a-z])", normalize(text)))


def check(original_cv: str, new_cv: str) -> list[Issue]:
    return [
        Issue("titles", "error", f"Kıdem/unvan ifadesi '{w}' orijinal CV'de olmadan eklendi.")
        for w in SENIORITY
        if count(new_cv, w) > count(original_cv, w)
    ]
