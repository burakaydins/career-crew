"""Live mock interview: the Interviewer agent asks the prepared questions one by one, the candidate
answers, and every answer is checked against the original CV. Reuses the Orchestrator's run_agent, so
it is the same envelope, providers and events as the main run. Nothing here writes state.json."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app import persist
from app.events import EventBus
from app.orchestrator import Orchestrator, RunFailed
from app.providers.base import Provider
from app.registry import Registry
from app.skills import RunState

DEFAULT_COUNT = 5
MAX_COUNT = 10
MAX_ANSWER_CHARS = 4000
FEEDBACK_FILE = "mulakat_geri_bildirim.md"
EVENT_LOG = "work/interview_events.jsonl"

# get_answer(n, question) returns the answer text, "" to skip the question, or None to end the interview.
GetAnswer = Callable[[int, str], "str | None"]


class InterviewError(RuntimeError):
    """The run folder cannot be used for an interview."""


@dataclass
class Prepared:
    text: str
    hint: str = ""


_HEADING = re.compile(r"^#{2,3}\s+(?:\d+[.)]\s*)?(.+?)\s*$")
_NUMBERED = re.compile(r"^(?:\d+[.)])\s+(?:\*\*)?(.+?)(?:\*\*)?\s*$")


def parse_questions(markdown: str) -> list[Prepared]:
    """Reads the questions out of output/interview.md: '## 1. Question' headings with the hints below,
    or a numbered list as a fallback."""
    for pattern in (_HEADING, _NUMBERED):
        out: list[Prepared] = []
        for line in markdown.splitlines():
            m = pattern.match(line.strip() if pattern is _NUMBERED else line)
            if m:
                out.append(Prepared(re.sub(r"[*_`]", "", m.group(1)).strip()))
            elif out and line.strip():
                out[-1].hint = (out[-1].hint + "\n" + line.strip()).strip()
        if out:
            return out
    return []


class InterviewSession:
    def __init__(self, orch: Orchestrator, questions: list[Prepared], count: int) -> None:
        self.orch = orch
        self.state: RunState = orch.state
        self.questions = questions[: max(1, min(count, MAX_COUNT))]
        self.qa: list[dict] = []
        self.bus = orch.bus

    @property
    def total(self) -> int:
        return len(self.questions)

    def ask(self, n: int) -> str:
        s = self.state
        s.iteration = n
        s.turn = {"prepared": {"text": self.questions[n - 1].text, "hint": self.questions[n - 1].hint}}
        if self.qa:
            last = self.qa[-1]
            s.turn["previous"] = {"question": last["question"], "answer": last["answer"], "verdict": last["verdict"]}
        self.orch.run_agent("interviewer", "ask_question")
        question = s.turn["asked"]
        self.bus.publish("interview_question", "interviewer", n=n, total=self.total, text=question)
        return question

    def answer(self, n: int, text: str) -> dict:
        s = self.state
        text = text.strip()[:MAX_ANSWER_CHARS]
        s.iteration = n
        s.turn["answer"] = text
        self.bus.publish("interview_answer", None, n=n, text=text)
        self.orch.run_agent("interviewer", "evaluate_answer")
        ev = s.turn["evaluation"]
        self.qa.append({"n": n, "question": s.turn["asked"], "answer": text, **ev})
        self.bus.publish("interview_evaluation", "interviewer", n=n, **ev)
        return ev

    def finish(self) -> Path | None:
        """Writes output/mulakat_geri_bildirim.md from what was answered. None when nothing was."""
        self.bus.publish("interview_finished", "code", answered=len(self.qa), total=self.total)
        if not self.qa:
            return None
        path = self.state.output / FEEDBACK_FILE
        path.write_text(build_feedback(self.state, self.qa, self.total), encoding="utf-8")
        self.bus.publish("interview_report", "code", path=f"output/{FEEDBACK_FILE}")
        return path


def run(session: InterviewSession, get_answer: GetAnswer) -> Path | None:
    """Asks questions until the count is reached or get_answer returns None. Always writes the feedback
    for whatever was answered, even when the model stops (limit, error) halfway."""
    try:
        session.bus.publish("interview_started", None, total=session.total, title=session.state.job.get("title", ""))
        for n in range(1, session.total + 1):
            question = session.ask(n)
            answer = get_answer(n, question)
            if answer is None:
                break
            if answer.strip():
                session.answer(n, answer)
    finally:
        session.finish()
    return session.state.output / FEEDBACK_FILE if session.qa else None


def open_session(run_dir: Path, provider: Provider, bus: EventBus, count: int = DEFAULT_COUNT) -> InterviewSession:
    """Rebuilds the run from work/state.json, reads (or regenerates) the questions."""
    if not run_dir.is_dir():
        raise InterviewError(f"Klasör bulunamadı: {run_dir}")
    try:
        state = persist.restore(run_dir, persist.read(run_dir))[0]
    except persist.StateError as e:
        raise InterviewError(str(e)) from e
    if not state.job or not state.cv_text:
        raise InterviewError("Bu çalıştırmada ilan ya da CV yok, mülakat yapılamaz. İlan okunmadan duran bir süreç olabilir.")
    state.output.mkdir(parents=True, exist_ok=True)
    orch = Orchestrator(provider, run_dir, state.job_text, state.cv_text, lambda *_: None, bus, Registry(lang=state.lang),
                        resume=(state, []), event_log=EVENT_LOG, persist_state=False)
    path = state.output / "interview.md"
    if not path.is_file():
        if not state.cv:
            raise InterviewError("Bu çalıştırmada uyarlanmış CV yok, soru hazırlanamaz. Önce süreci bitirin.")
        try:
            orch.run_agent("interviewer", "prepare_interview")
        except RunFailed as e:
            raise InterviewError(str(e)) from e
    questions = parse_questions(path.read_text(encoding="utf-8"))
    if not questions:
        raise InterviewError(f"{path} içinde soru bulunamadı (beklenen biçim: '## 1. Soru' başlıkları).")
    return InterviewSession(orch, questions, count)


LABELS = {
    "tr": {
        "title": "Deneme mülakatı geri bildirimi", "summary": "{a}/{t} soru cevaplandı. Güçlü: {s}, orta: {o}, zayıf: {w}. CV'de olmayan iddia içeren cevap: {f}.",
        "strong": "Güçlü cevaplar", "weak": "Geliştirilecek cevaplar", "flagged": "CV'de olmayan iddialar",
        "none": "Yok.", "claim": "İddia", "framing": "Dürüst çerçeve", "all": "Tüm cevaplar", "q": "Soru", "a": "Cevabın",
        "v": {"strong": "güçlü", "ok": "orta", "weak": "zayıf"}, "check": "Doğrula",
        "note": "Yapay zekâ değerlendirmesidir, hatalı olabilir. Önerilen çerçeveler yalnızca CV'ndeki gerçek deneyime dayanır, yine de kendin kontrol et.",
    },
    "en": {
        "title": "Mock interview feedback", "summary": "{a}/{t} questions answered. Strong: {s}, ok: {o}, weak: {w}. Answers with claims not in the CV: {f}.",
        "strong": "Strong answers", "weak": "Answers to improve", "flagged": "Claims that are not in the CV",
        "none": "None.", "claim": "Claim", "framing": "Honest framing", "all": "All answers", "q": "Question", "a": "Your answer",
        "v": {"strong": "strong", "ok": "ok", "weak": "weak"}, "check": "Check",
        "note": "This is an AI evaluation and can be wrong. Suggested framings rely only on real experience in your CV, check them yourself anyway.",
    },
}


def build_feedback(state: RunState, qa: list[dict], total: int) -> str:
    L = LABELS["en" if state.lang == "en" else "tr"]
    count = lambda v: sum(1 for x in qa if x["verdict"] == v)
    flagged = [x for x in qa if x["flags"] or x["code_flags"]]
    lines = [f"# {L['title']}: {state.job.get('title', '')}".rstrip(": "), "",
             L["summary"].format(a=len(qa), t=total, s=count("strong"), o=count("ok"), w=count("weak"), f=len(flagged)), ""]

    def section(name: str, items: list[str]) -> None:
        lines.extend([f"## {name}", "", *(items or [L["none"]]), ""])

    section(L["strong"], [f"- {x['question']}\n  {x['feedback']}" for x in qa if x["verdict"] == "strong"])
    section(L["weak"], [f"- {x['question']}\n  {x['feedback']}" for x in qa if x["verdict"] != "strong"])
    items = []
    for x in flagged:
        block = [f"- {x['question']}"]
        block += [f"  - {L['claim']}: {f['claim']}" + (f" ({f['why']})" if f["why"] else "") for f in x["flags"]]
        block += [f"  - {L['check']}: {c}" for c in x["code_flags"]]
        if x["framing"]:
            block.append(f"  - {L['framing']}: {x['framing']}")
        items.append("\n".join(block))
    section(L["flagged"], items)
    lines.append(f"## {L['all']}\n")
    for x in qa:
        lines += [f"### {x['n']}. {x['question']}", "", f"{L['a']}: {x['answer']}", "", f"**{L['v'][x['verdict']]}**: {x['feedback']}", ""]
    lines += ["---", L["note"], ""]
    return "\n".join(lines)
