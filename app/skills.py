"""Per-skill prompt builders and result handlers.

A prompt builder turns run state into the user prompt. A handler validates the
agent's envelope, writes the allowed files and updates run state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.checks import CheckReport
from app.providers.base import AgentResult, ProviderError


@dataclass
class RunState:
    job_text: str
    cv_text: str
    run_dir: Path
    iteration: int = 0
    job: dict = field(default_factory=dict)
    cv: str = ""
    claims: list[dict] = field(default_factory=list)
    checks: CheckReport | None = None
    verdict: dict = field(default_factory=dict)
    score: int = 0
    missing: list[str] = field(default_factory=list)
    rounds: list[dict] = field(default_factory=list)
    best: dict | None = None
    converged: bool = False
    plateau: bool = False
    feedback: dict[str, str] = field(default_factory=dict)
    usage: list[dict] = field(default_factory=list)
    lang: str = "tr"
    lesson_candidates: list[dict] = field(default_factory=list)
    lesson_rejected: list[dict] = field(default_factory=list)
    saved_lessons: list[str] = field(default_factory=list)  # not persisted
    turn: dict = field(default_factory=dict)  # current mock-interview turn, not persisted

    @property
    def work(self) -> Path:
        return self.run_dir / "work"

    @property
    def output(self) -> Path:
        return self.run_dir / "output"

    @property
    def no_fabrication(self) -> bool:
        return bool(self.checks) and not self.checks.errors and self.verdict.get("decision") == "approve"


# Tag names of the user prompt, in English for the English prompt set.
TAGS_EN = {
    "ilan": "job_posting", "duzeltme": "correction", "onceki_okuma": "previous_reading",
    "orijinal_cv": "original_cv", "ilan_ozeti": "job_summary", "onceki_cv": "previous_cv",
    "geri_bildirim": "feedback", "yeni_cv": "new_cv", "kod_kontrolleri": "code_checks",
    "cv": "cv", "cvde_olmayan_ilan_terimleri": "posting_terms_missing_from_cv",
    "kullanici_duzeltmesi": "user_correction", "turlar": "rounds", "kayitli_dersler": "saved_lessons",
    "hazirlanan_soru": "prepared_question", "onceki_cevap": "previous_exchange", "soru": "question",
    "cevap_ipucu": "answer_hint", "aday_cevabi": "candidate_answer",
}


def _block(s: "RunState", tag: str, content: str) -> str:
    if s.lang == "en":
        tag = TAGS_EN.get(tag, tag)
    return f"<{tag}>\n{content.strip()}\n</{tag}>"


def _t(s: "RunState", tr: str, en: str) -> str:
    return en if s.lang == "en" else tr


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    raise ProviderError("Liste beklenen alanda başka bir değer var")


def _require_file(result: AgentResult, name: str) -> str:
    content = result.files.get(name, "").strip()
    if not content:
        raise ProviderError(f"Ajan '{name}' dosyasını üretmedi")
    return content + "\n"


# ---- analyze_job -------------------------------------------------------------

def prompt_analyze_job(s: RunState) -> str:
    parts = [_t(s, "Görev: analyze_job. İlanı oku ve şemaya göre çıkar.", "Task: analyze_job. Read the posting and extract it into the schema."), _block(s, "ilan", s.job_text)]
    if note := s.feedback.get("confirm_job"):
        parts += [_t(s, "Kullanıcı önceki okumayı düzeltti:", "The user corrected the previous reading:"), _block(s, "duzeltme", note), _block(s, "onceki_okuma", _json(s.job))]
    return "\n\n".join(parts)


def apply_analyze_job(s: RunState, r: AgentResult) -> None:
    job = r.data
    if not job.get("title") or not isinstance(job.get("required_skills"), list):
        raise ProviderError("İlan Analisti geçerli bir job.json üretmedi")
    for key in ("required_skills", "preferred_skills", "keywords"):
        job[key] = _str_list(job.get(key))
    s.job = job
    (s.work / "job.json").write_text(_json(job) + "\n", encoding="utf-8")


# ---- tailor_cv ---------------------------------------------------------------

def feedback_for_writer(s: RunState) -> list[str]:
    items = [i.message for i in s.checks.errors] if s.checks else []
    items += s.verdict.get("issues", [])
    items += [_t(s, f"İşe alım eksiği: {m}", f"Hiring gap: {m}") for m in s.missing]
    return items


def prompt_tailor_cv(s: RunState) -> str:
    parts = [
        _t(s, "Görev: tailor_cv. Orijinal CV'yi ilana göre uyarla.", "Task: tailor_cv. Tailor the original CV to the posting."),
        _block(s, "orijinal_cv", s.cv_text),
        _block(s, "ilan_ozeti", _json(s.job)),
    ]
    if s.iteration > 1 and s.cv:
        parts += [
            _t(s, f"Bu {s.iteration}. tur. Önceki sürüm ve geri bildirim aşağıda.", f"This is round {s.iteration}. The previous version and feedback follow."),
            _block(s, "onceki_cv", s.cv),
            _block(s, "geri_bildirim", "\n".join(f"- {x}" for x in feedback_for_writer(s))),
        ]
    return "\n\n".join(parts)


def apply_tailor_cv(s: RunState, r: AgentResult) -> None:
    cv = _require_file(r, "cv.md")
    claims = r.data.get("claims")
    if not isinstance(claims, list) or not all(isinstance(c, dict) for c in claims):
        raise ProviderError("CV Yazarı geçerli bir 'claims' listesi üretmedi")
    s.cv, s.claims = cv, claims
    s.verdict, s.score, s.missing = {}, 0, []
    (s.work / f"cv_v{s.iteration}.md").write_text(cv, encoding="utf-8")
    (s.work / f"claims_v{s.iteration}.json").write_text(_json(claims) + "\n", encoding="utf-8")
    (s.work / "claims.json").write_text(_json(claims) + "\n", encoding="utf-8")


# ---- verify ------------------------------------------------------------------

def prompt_verify(s: RunState) -> str:
    checks = s.checks.to_dict() if s.checks else {}
    return "\n\n".join([
        _t(s, "Görev: verify. Uyarlanmış CV'de uydurma var mı karar ver.", "Task: verify. Decide whether the tailored CV contains fabrication."),
        _block(s, "orijinal_cv", s.cv_text),
        _block(s, "yeni_cv", s.cv),
        _block(s, "claims", _json(s.claims)),
        _block(s, "kod_kontrolleri", _json(checks["issues"] if checks else [])),
    ])


def apply_verify(s: RunState, r: AgentResult) -> None:
    decision = r.data.get("decision")
    if decision not in ("approve", "reject"):
        raise ProviderError("Doğrulayıcı 'approve' ya da 'reject' kararı vermedi")
    verdict = {"decision": decision, "reason": str(r.data.get("reason", "")), "issues": _str_list(r.data.get("issues"))}
    # Rule: the verifier cannot approve while code checks report errors.
    if decision == "approve" and s.checks and s.checks.errors:
        verdict["decision"] = "reject"
        verdict["overridden"] = True
        verdict["reason"] = "Kod kontrollerinde açık sorun varken onay verilemez."
    s.verdict = verdict


# ---- score -------------------------------------------------------------------

def prompt_score(s: RunState) -> str:
    return "\n\n".join([
        _t(s, "Görev: score. CV'yi bu ilan için puanla.", "Task: score. Score the CV for this posting."),
        _block(s, "ilan_ozeti", _json(s.job)),
        _block(s, "cv", s.cv),
    ])


def apply_score(s: RunState, r: AgentResult) -> None:
    try:
        score = int(r.data.get("score"))
    except (TypeError, ValueError) as e:
        raise ProviderError("İşe Alım Müdürü geçerli bir puan vermedi") from e
    s.score = max(0, min(100, score))
    s.missing = _str_list(r.data.get("missing"))[:3]


# ---- write_letter / prepare_interview -----------------------------------------

def prompt_write_letter(s: RunState) -> str:
    return "\n\n".join([
        _t(s, "Görev: write_letter. Ön yazıyı hazırla.", "Task: write_letter. Write the cover letter."),
        _block(s, "ilan_ozeti", _json(s.job)),
        _block(s, "cv", s.cv),
    ])


def apply_write_letter(s: RunState, r: AgentResult) -> None:
    (s.output / "cover_letter.md").write_text(_require_file(r, "cover_letter.md"), encoding="utf-8")


def prompt_prepare_interview(s: RunState) -> str:
    missing = s.checks.missing_keywords if s.checks else []
    return "\n\n".join([
        _t(s, "Görev: prepare_interview. Mülakat hazırlığını yap.", "Task: prepare_interview. Prepare the interview material."),
        _block(s, "ilan_ozeti", _json(s.job)),
        _block(s, "cv", s.cv),
        _block(s, "cvde_olmayan_ilan_terimleri", ", ".join(missing) or _t(s, "yok", "none")),
    ])


def apply_prepare_interview(s: RunState, r: AgentResult) -> None:
    (s.output / "interview.md").write_text(_require_file(r, "interview.md"), encoding="utf-8")


# ---- extract_lessons ----------------------------------------------------------

def prompt_extract_lessons(s: RunState) -> str:
    existing = s.saved_lessons
    rounds = [
        {"round": r["iteration"], "code_errors": [i.message for i in r["checks"].errors] if r["checks"] else [],
         "verifier_issues": r["verdict"].get("issues", []), "hiring_gaps": r["missing"]}
        for r in s.rounds
    ]
    return "\n\n".join([
        _t(s, "Görev: extract_lessons. Bu çalıştırmadan en fazla 3 stil ya da tercih dersi çıkar.",
           "Task: extract_lessons. Extract at most 3 style or preference lessons from this run."),
        _block(s, "kullanici_duzeltmesi", s.feedback.get("confirm_job", "-")),
        _block(s, "turlar", _json(rounds)),
        _block(s, "kayitli_dersler", "\n".join(f"- {x}" for x in (existing or [])) or _t(s, "yok", "none")),
    ])


def apply_extract_lessons(s: RunState, r: AgentResult) -> None:
    raw = r.data.get("lessons")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ProviderError("'lessons' bir liste olmalı")
    s.lesson_candidates = [c for c in raw if isinstance(c, dict)]


# ---- mock interview ------------------------------------------------------------

VERDICTS = ("strong", "ok", "weak")
NO_NEW_NUMBERS = ("Öneri CV'de olmayan bir rakam içerdiği için gösterilmedi. Konuyu CV'deki gerçek deneyimle anlat.",
                  "The suggestion was withheld because it contains a number that is not in the CV. Tell it with the real experience from the CV.")


def prompt_ask_question(s: RunState) -> str:
    q = s.turn["prepared"]
    block = q["text"] + (f"\n{q['hint']}" if q.get("hint") else "")
    parts = [
        _t(s, "Görev: ask_question. Sıradaki deneme mülakatı sorusunu adaya sor.", "Task: ask_question. Ask the candidate the next mock-interview question."),
        _block(s, "ilan_ozeti", _json(s.job)),
        _block(s, "hazirlanan_soru", block),
    ]
    if prev := s.turn.get("previous"):
        parts.append(_block(s, "onceki_cevap", f"{prev['question']}\n{prev['answer'][:600]}\n{prev['verdict']}"))
    return "\n\n".join(parts)


def apply_ask_question(s: RunState, r: AgentResult) -> None:
    question = str(r.data.get("question") or r.message).strip()
    if not question:
        raise ProviderError("Mülakatçı soru üretmedi")
    s.turn["asked"] = question
    r.message = question  # what the terminal and the chat show: always the question, whatever else the model said


def prompt_evaluate_answer(s: RunState) -> str:
    t = s.turn
    return "\n\n".join([
        _t(s, "Görev: evaluate_answer. Adayın cevabını orijinal CV'ye göre değerlendir.", "Task: evaluate_answer. Evaluate the candidate's answer against the original CV."),
        _block(s, "orijinal_cv", s.cv_text),
        _block(s, "ilan_ozeti", _json(s.job)),
        _block(s, "soru", t["asked"]),
        _block(s, "cevap_ipucu", t["prepared"].get("hint") or "-"),
        _block(s, "aday_cevabi", t["answer"]),
    ])


def apply_evaluate_answer(s: RunState, r: AgentResult) -> None:
    from app.checks.numbers import numbers as _numbers

    # "N+1", "S3": a digit glued to a letter or "+" is a name, not a figure the candidate claims.
    numbers = lambda text: _numbers(re.sub(r"\b[A-Za-z]\s?\+\s?\d+", " ", text))

    verdict = r.data.get("verdict")
    if verdict not in VERDICTS:
        raise ProviderError("Mülakatçı geçerli bir değerlendirme ('strong', 'ok' ya da 'weak') vermedi")
    flags = []
    for f in r.data.get("flags") or []:
        if isinstance(f, dict) and str(f.get("claim", "")).strip():
            flags.append({"claim": str(f["claim"]).strip(), "why": str(f.get("why", "")).strip()})
        elif isinstance(f, str) and f.strip():
            flags.append({"claim": f.strip(), "why": ""})
    # Code backstop 1: numbers the candidate states that the CV does not contain are always shown.
    cv_numbers = numbers(s.cv_text)
    answer_numbers = sorted(numbers(s.turn["answer"]) - cv_numbers)
    code_flags = [_t(s, f"'{n}' rakamı CV'nde yok. Gerçekse CV'ne ekle, değilse söyleme.",
                     f"The number '{n}' is not in your CV. If it is true add it to the CV, otherwise do not say it.") for n in answer_numbers]
    framing = str(r.data.get("framing") or "").strip()
    # Code backstop 2: a suggested framing may not bring in numbers that are not in the CV.
    if framing and numbers(framing) - cv_numbers:
        framing = _t(s, *NO_NEW_NUMBERS)
    if not flags and not code_flags:
        framing = ""
    s.turn["evaluation"] = {"verdict": verdict, "feedback": r.message, "flags": flags, "code_flags": code_flags, "framing": framing}


SKILLS: dict[str, tuple[Callable[[RunState], str], Callable[[RunState, AgentResult], None]]] = {
    "analyze_job": (prompt_analyze_job, apply_analyze_job),
    "tailor_cv": (prompt_tailor_cv, apply_tailor_cv),
    "verify": (prompt_verify, apply_verify),
    "score": (prompt_score, apply_score),
    "write_letter": (prompt_write_letter, apply_write_letter),
    "prepare_interview": (prompt_prepare_interview, apply_prepare_interview),
    "extract_lessons": (prompt_extract_lessons, apply_extract_lessons),
    "ask_question": (prompt_ask_question, apply_ask_question),
    "evaluate_answer": (prompt_evaluate_answer, apply_evaluate_answer),
}
