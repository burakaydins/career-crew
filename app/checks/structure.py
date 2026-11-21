"""Structure: length and sections that disappeared."""

from __future__ import annotations

import re

from app.checks import Issue
from app.checks.text import normalize

MAX_WORDS = 1000
HEADING = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def headings(cv: str) -> set[str]:
    return {normalize(h) for h in HEADING.findall(cv)}


def check(original_cv: str, new_cv: str) -> list[Issue]:
    issues = []
    words = len(new_cv.split())
    if words > MAX_WORDS:
        issues.append(Issue("structure", "warning", f"CV {words} kelime, 2 sayfayı aşabilir (sınır {MAX_WORDS})."))
    original_sections = {normalize(h) for h in re.findall(r"^##\s+(.+)$", original_cv, re.MULTILINE)}
    for section in sorted(original_sections - headings(new_cv)):
        issues.append(Issue("structure", "warning", f"'{section}' bölümü yeni CV'de yok."))
    return issues
