"""Layer 1: every claim must quote evidence that really exists in the original CV."""

from __future__ import annotations

from difflib import SequenceMatcher

from app.checks import Issue
from app.checks.text import normalize

FUZZY_THRESHOLD = 0.85
MIN_WORDS = 3  # a one- or two-word quote ("Python", "test") proves nothing


def best_match_ratio(quote: str, source: str) -> float:
    """Highest similarity between `quote` and any same-length word window of `source`."""
    q, s = normalize(quote), normalize(source)
    if not q:
        return 0.0
    # Whole words only: "test" must not match inside "testleri".
    if f" {q} " in f" {s} ":
        return 1.0
    q_words, s_words = q.split(), s.split()
    n = len(q_words)
    best = 0.0
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(s_words) - size + 1)):
            window = " ".join(s_words[i : i + size])
            best = max(best, SequenceMatcher(None, q, window).ratio())
    return best


def check(original_cv: str, claims: list[dict]) -> list[Issue]:
    issues = []
    if not claims:
        return [Issue("evidence", "error", "claims.json boş: hiçbir madde kanıta bağlanmamış.")]
    for c in claims:
        claim, quote = str(c.get("claim", "")).strip(), str(c.get("evidence", "")).strip()
        if not quote:
            issues.append(Issue("evidence", "error", f"Kanıt alıntısı yok: '{claim}'"))
        elif len(normalize(quote).split()) < MIN_WORDS:
            issues.append(Issue("evidence", "error",
                                f"Kanıt çok kısa (en az {MIN_WORDS} kelime): '{quote}' → '{claim}'"))
        elif best_match_ratio(quote, original_cv) < FUZZY_THRESHOLD:
            issues.append(Issue("evidence", "error", f"Kanıt orijinal CV'de bulunamadı: '{quote}'"))
    return issues
