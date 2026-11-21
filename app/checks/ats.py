"""ATS score: share of job keywords found in the CV."""

from __future__ import annotations

from app.checks.leakage import job_terms
from app.checks.text import contains_term


def score(cv: str, job: dict) -> tuple[float, list[str], list[str]]:
    terms = job_terms(job)
    if not terms:
        return 0.0, [], []
    matched = [t for t in terms if contains_term(cv, t)]
    missing = [t for t in terms if t not in matched]
    return round(100 * len(matched) / len(terms), 1), matched, missing
