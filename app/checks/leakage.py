"""Job-keyword leakage: terms from the posting that appear in the new CV but never in the original."""

from __future__ import annotations

import re

from app.checks import Issue
from app.checks.text import contains_term, normalize

# A term counts as present in the original CV if any of these narrower terms is there.
IMPLIED_BY = {
    "sql": ["postgresql", "mysql", "sqlite", "mssql", "oracle", "mariadb"],
    "rest": ["rest api"],
    "api": ["rest api", "graphql"],
    "test": ["pytest", "unittest", "birim test", "unit test"],
    "git": ["github", "gitlab"],
}


def job_terms(job: dict) -> list[str]:
    seen, terms = set(), []
    for key in ("required_skills", "preferred_skills", "keywords"):
        for term in job.get(key) or []:
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)
    return terms


def in_original(term: str, original_cv: str) -> bool:
    if contains_term(original_cv, term):
        return True
    return any(contains_term(original_cv, alt) for alt in IMPLIED_BY.get(term.lower(), []))


SKILLS_HEADING = re.compile(r"^#{2,3}\s*(beceri|yetenek|yetkinlik|teknoloji|skills|technical|tech stack)", re.I)
# Acronyms (AWS, gRPC), CamelCase (PostgreSQL, FastAPI), names with digits or symbols (C++, S3, Node.js)
TECH_TOKEN = re.compile(r"\b(?:[A-Z]{2,}[a-z]*|[a-z]+[A-Z]{2,}|[A-Z][a-z]+[A-Z][A-Za-z]*|[A-Za-z]+(?:\+\+|#|\.js|\d+))\b|\b[A-Za-z]+(?:\+\+|#)")


def skills_items(cv: str) -> list[str]:
    items, inside = [], False
    for line in cv.splitlines():
        if line.startswith("#"):
            inside = SKILLS_HEADING.match("## " + normalize(line.lstrip("#"))) is not None
            continue
        if inside and line.strip():
            line = re.sub(r"[*_`]", "", line)  # **bold** markers
            line = re.sub(r"^\s*[-•]?\s*[^:,;|]{1,40}:\s+", "", line)  # "- Networking: URLSession, ..." keeps the skills only
            items += [x.strip(" -*.") for x in re.split(r"[,;|•]", line)]
    return [x for x in items if x]


def new_terms(original_cv: str, new_cv: str, job: dict) -> list[str]:
    """Technology-like terms in the new CV that the original never mentions."""
    known = {t.lower() for t in job_terms(job)}  # those are reported by check() already
    candidates = skills_items(new_cv)
    for b in re.findall(r"^\s*[-*]\s+(.+)$", new_cv, re.MULTILINE):
        candidates += TECH_TOKEN.findall(b)
    seen, out = set(), []
    for term in candidates:
        key = term.lower()
        if key in seen or key in known or len(key) < 2:
            continue
        seen.add(key)
        if not in_original(term, original_cv):
            out.append(term)
    return out


def check_new_terms(original_cv: str, new_cv: str, job: dict) -> list[Issue]:
    return [
        Issue("leakage", "warning", f"'{term}' orijinal CV'de geçmiyor. Gerçekten varsa orijinal CV'ye ekleyin.")
        for term in new_terms(original_cv, new_cv, job)
    ]


def check(original_cv: str, new_cv: str, job: dict) -> list[Issue]:
    return [
        Issue("leakage", "error", f"'{term}' ilanda var ama orijinal CV'de yok (sızıntı).")
        for term in job_terms(job)
        if contains_term(new_cv, term) and not in_original(term, original_cv)
    ]
