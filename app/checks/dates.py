"""Date consistency: new years and inflated "N years of experience" claims."""

from __future__ import annotations

import datetime as dt
import re

from app.checks import Issue
from app.checks.text import normalize

YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20\d\d)(?!\d)")
PRESENT = r"(?:gunumuz|halen|devam|present|current|now|today)"
RANGE = re.compile(rf"(19[5-9]\d|20\d\d)\s*-?\s*(19[5-9]\d|20\d\d|{PRESENT})")
YEARS_CLAIM = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\+?\s*(?:yil|yillik|years?|yrs)")
EXPERIENCE_HEADING = re.compile(r"^#+\s*(deneyim|is deneyimi|experience|work experience)", re.I)


def years(text: str) -> set[str]:
    return set(YEAR.findall(text))


def years_claims(text: str) -> list[float]:
    return [float(n) for n in YEARS_CLAIM.findall(normalize(text))]


def experience_span(cv: str, today: dt.date | None = None) -> int | None:
    """Years between the first start and the last end inside the experience section."""
    current = (today or dt.date.today()).year
    section, inside = [], False
    for line in cv.splitlines():
        if line.startswith("## "):
            inside = EXPERIENCE_HEADING.match("## " + normalize(line[3:])) is not None
            continue
        if inside:
            section.append(line)
    starts, ends = [], []
    for a, b in RANGE.findall(normalize("\n".join(section))):
        starts.append(int(a))
        ends.append(current if not b.isdigit() else int(b))
    if not starts:
        return None
    return max(ends) - min(starts)


def check(original_cv: str, new_cv: str, today: dt.date | None = None) -> list[Issue]:
    issues = [
        Issue("dates", "error", f"Yıl {y} orijinal CV'de yok.")
        for y in sorted(years(new_cv) - years(original_cv))
    ]
    original_claims = years_claims(original_cv)
    limit = max(original_claims) if original_claims else experience_span(original_cv, today)
    if limit is not None:
        for n in sorted(set(years_claims(new_cv))):
            if n > limit:
                issues.append(Issue("dates", "error",
                                    f"'{n:g} yıl' iddiası orijinal CV ile uyuşmuyor (en fazla {limit:g} yıl)."))
    return issues
