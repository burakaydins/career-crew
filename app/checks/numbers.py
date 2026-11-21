"""New numbers and percentages that do not exist in the original CV."""

from __future__ import annotations

import re

from app.checks import Issue
from app.checks.text import normalize

NUMBER = re.compile(r"(?<![0-9a-z])%?\s?(\d+(?:[.,]\d+)?)\s?%?(?!\d)(\s*(?:yil|yillik|years?|yrs))?")


def numbers(text: str, *, skip_years_claims: bool = False) -> set[str]:
    found = set()
    for value, years_suffix in NUMBER.findall(normalize(text)):
        if skip_years_claims and years_suffix:
            continue  # "N yıl" is handled by the dates check
        found.add(value.replace(",", "."))
    return found


def check(original_cv: str, new_cv: str) -> list[Issue]:
    new = numbers(new_cv, skip_years_claims=True) - numbers(original_cv)
    return [Issue("numbers", "error", f"'{n}' rakamı orijinal CV'de yok.") for n in sorted(new)]
