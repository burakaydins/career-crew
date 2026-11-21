"""Deterministic checks (no LLM). Layer 1 and 2 of the anti-fabrication design."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Issue:
    check: str
    severity: str  # "error" blocks approval, "warning" is informational
    message: str


@dataclass
class CheckReport:
    issues: list[Issue] = field(default_factory=list)
    ats_before: float = 0.0
    ats_after: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def to_dict(self) -> dict:
        return asdict(self)


def run_all(original_cv: str, new_cv: str, claims: list[dict], job: dict) -> CheckReport:
    from app.checks import ats, coverage, dates, evidence, leakage, numbers, structure, titles

    report = CheckReport()
    report.issues += coverage.check(new_cv, claims)
    report.issues += evidence.check(original_cv, claims)
    report.issues += leakage.check(original_cv, new_cv, job)
    report.issues += leakage.check_new_terms(original_cv, new_cv, job)
    report.issues += dates.check(original_cv, new_cv)
    report.issues += numbers.check(original_cv, new_cv)
    report.issues += titles.check(original_cv, new_cv)
    report.issues += structure.check(original_cv, new_cv)
    report.ats_before, _, _ = ats.score(original_cv, job)
    report.ats_after, report.matched_keywords, report.missing_keywords = ats.score(new_cv, job)
    return report
