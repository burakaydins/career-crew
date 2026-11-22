"""Saves and restores a run so it can continue after a pause or a crash (work/state.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.checks import CheckReport, Issue
from app.skills import RunState

VERSION = 1
FILE = "state.json"


class StateError(RuntimeError):
    """state.json is missing, damaged or from an incompatible version."""


def _checks_to(c: CheckReport | None) -> dict | None:
    return c.to_dict() if c else None


def _checks_from(d: dict | None) -> CheckReport | None:
    if d is None:
        return None
    return CheckReport(
        issues=[Issue(**i) for i in d["issues"]], ats_before=d["ats_before"], ats_after=d["ats_after"],
        matched_keywords=d["matched_keywords"], missing_keywords=d["missing_keywords"],
    )


def dump(s: RunState, completed: list[str], status: str, provider: str, note: str = "") -> dict:
    rounds = [{**r, "checks": _checks_to(r["checks"])} for r in s.rounds]
    best = next((i for i, r in enumerate(s.rounds) if r is s.best), None)
    return {
        "version": VERSION, "status": status, "provider": provider, "note": note, "completed": completed,
        "state": {
            "job_text": s.job_text, "cv_text": s.cv_text, "iteration": s.iteration, "job": s.job, "cv": s.cv,
            "claims": s.claims, "checks": _checks_to(s.checks), "verdict": s.verdict, "score": s.score,
            "missing": s.missing, "rounds": rounds, "best": best, "converged": s.converged, "plateau": s.plateau,
            "feedback": s.feedback, "usage": s.usage, "lang": s.lang,
            "lesson_candidates": s.lesson_candidates, "lesson_rejected": s.lesson_rejected,
        },
    }


def save(run_dir: Path, data: dict) -> None:
    path = run_dir / "work" / FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read(run_dir: Path) -> dict:
    path = run_dir / "work" / FILE
    if not path.is_file():
        raise StateError(f"Durum dosyası yok: {path}. Bu klasör devam ettirilemez.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise StateError(f"Durum dosyası bozuk ({path}): {e}") from e
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise StateError(f"Durum dosyası bu sürümle uyumsuz ({path}): sürüm {data.get('version') if isinstance(data, dict) else '?'}, beklenen {VERSION}")
    if not isinstance(data.get("state"), dict) or not isinstance(data.get("completed"), list):
        raise StateError(f"Durum dosyası eksik alanlar içeriyor ({path})")
    return data


def restore(run_dir: Path, data: dict) -> tuple[RunState, list[str]]:
    d = data["state"]
    try:
        s = RunState(job_text=d["job_text"], cv_text=d["cv_text"], run_dir=run_dir, lang=d["lang"])
        s.iteration, s.job, s.cv, s.claims = d["iteration"], d["job"], d["cv"], d["claims"]
        s.checks, s.verdict, s.score, s.missing = _checks_from(d["checks"]), d["verdict"], d["score"], d["missing"]
        s.rounds = [{**r, "checks": _checks_from(r["checks"])} for r in d["rounds"]]
        s.best = s.rounds[d["best"]] if d["best"] is not None else None
        s.converged, s.plateau, s.feedback, s.usage = d["converged"], d["plateau"], d["feedback"], d["usage"]
        s.lesson_candidates, s.lesson_rejected = d["lesson_candidates"], d["lesson_rejected"]
        completed = [str(x) for x in data["completed"]]
    except (KeyError, TypeError, IndexError, ValueError) as e:
        raise StateError(f"Durum dosyası bozuk ({run_dir / 'work' / FILE}): {type(e).__name__} {e}") from e
    return s, completed
