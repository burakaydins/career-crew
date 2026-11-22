"""Runs the career workflow: wires agents, checks, the event bus and the run folder."""

from __future__ import annotations

import datetime as dt
import re
import json
import shutil
import threading
from pathlib import Path
from typing import Callable

from app import persist
from app import report as report_mod
from app.checks import run_all
from app.events import EventBus, JsonlSink
from app.memory import LessonStore, MemoryError_, screen
from app.providers.base import AgentRequest, Provider, ProviderError, RateLimited
from app.registry import Registry
from app.skills import SKILLS, RunState
from app.tasks import DataPart, Message, Task, TaskState, TextPart
from app.workflow import CodeStep, Loop, Parallel, Sequential, Step, UserGate

TARGET_SCORE = 80
MAX_ROUNDS = 3

AskFn = Callable[[str, RunState], "str | None"]


class RunFailed(RuntimeError):
    pass


class RunPaused(RuntimeError):
    """The usage limit is reached. The run state is saved and `--devam` continues it."""

    def __init__(self, message: str, run_dir: Path) -> None:
        super().__init__(message)
        self.run_dir = run_dir


def slugify(text: str) -> str:
    text = text.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "run"


def create_run_dir(base: Path, job_file: Path, cv_file: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"{stamp}_{slugify(job_file.stem)}"
    run_dir, n = base / name, 1
    while run_dir.exists():  # two runs in the same second must not share a folder
        n += 1
        run_dir = base / f"{name}-{n}"
    for sub in ("inputs", "work", "output"):
        (run_dir / sub).mkdir(parents=True)
    shutil.copy(job_file, run_dir / "inputs" / f"ilan{job_file.suffix}")
    shutil.copy(cv_file, run_dir / "inputs" / f"cv{cv_file.suffix}")
    return run_dir


# ---- code steps ----------------------------------------------------------------

def run_checks(ctx: "Orchestrator") -> None:
    s = ctx.state
    s.checks = run_all(s.cv_text, s.cv, s.claims, s.job)
    ctx.bus.publish(
        "checks",
        "code",
        errors=[i.message for i in s.checks.errors],
        warnings=[i.message for i in s.checks.issues if i.severity != "error"],
        ats_before=s.checks.ats_before,
        ats_after=s.checks.ats_after,
    )


def record_round(ctx: "Orchestrator") -> None:
    s = ctx.state
    round_ = {
        "iteration": s.iteration,
        "cv": s.cv,
        "claims": s.claims,
        "checks": s.checks,
        "verdict": s.verdict,
        "errors": len(s.checks.errors) if s.checks else 0,
        "decision": s.verdict.get("decision", "-"),
        "score": s.score,
        "missing": s.missing,
        "clean": s.no_fabrication,
    }
    s.rounds.append(round_)
    ctx.bus.publish("round_recorded", "code", iteration=s.iteration, score=s.score, errors=round_["errors"],
                    decision=round_["decision"], clean=round_["clean"])
    # Best = clean beats unclean, then fewer code errors, then higher score.
    key = lambda r: (r["clean"], -r["errors"], r["score"])
    if s.best is None or key(round_) > key(s.best):
        s.best = round_


def finalize_cv(ctx: "Orchestrator") -> None:
    s = ctx.state
    s.converged = bool(s.rounds) and s.rounds[-1]["clean"] and s.rounds[-1]["score"] >= TARGET_SCORE
    best = s.best
    s.cv, s.claims, s.checks, s.verdict = best["cv"], best["claims"], best["checks"], best["verdict"]
    s.score, s.missing = best["score"], best["missing"]
    (s.output / "cv.md").write_text(s.cv, encoding="utf-8")
    s.plateau = not s.converged and len(s.rounds) < MAX_ROUNDS
    if s.plateau:
        ctx.bus.publish("warning", "code", text=(
            f"Puan {len(s.rounds)}. turda artmadı, döngü erken durduruldu. Kalan eksikler gerçek: "
            f"orijinal CV'de karşılıkları yok. {best['iteration']}. tur kullanılıyor (puan {best['score']})."
        ))
    elif not s.converged:
        ctx.bus.publish("warning", "code", text=(
            f"{MAX_ROUNDS} turda hedefe ulaşılamadı. {best['iteration']}. tur kullanılıyor "
            f"(puan {best['score']}, {best['errors']} kod hatası)."
        ))


def write_report(ctx: "Orchestrator") -> None:
    s = ctx.state
    (s.output / "report.md").write_text(report_mod.build(s), encoding="utf-8")
    ctx.bus.publish("report", "code", path="output/report.md")


def round_done(s: RunState) -> bool:
    return s.no_fabrication and s.score >= TARGET_SCORE


def plateau(s: RunState) -> bool:
    """Two clean rounds in a row and the score did not rise: the remaining gaps are real,
    so another rewrite only spends tokens."""
    if len(s.rounds) < 2:
        return False
    prev, last = s.rounds[-2], s.rounds[-1]
    return prev["clean"] and last["clean"] and last["score"] <= prev["score"]


def make_pdfs(ctx: "Orchestrator") -> None:
    """PDF is a convenience: a failure here must not fail a run whose package is complete."""
    from app import pdf

    try:
        made = pdf.render_outputs(ctx.state.output)
    except Exception as e:
        ctx.bus.publish("warning", "code", text=f"PDF üretilemedi: {e}")
        return
    ctx.bus.publish("pdf", "code", files=made)


def career_flow(with_pdf: bool = False) -> Sequential:
    return Sequential(
        Step("job_analyst", "analyze_job"),
        UserGate("confirm_job", retry=Step("job_analyst", "analyze_job")),
        Loop(
            Step("cv_writer", "tailor_cv"),
            CodeStep("checks", run_checks),
            Parallel(Step("verifier", "verify"), Step("recruiter", "score")),
            CodeStep("record_round", record_round),
            until=round_done,
            give_up=plateau,
            max_iterations=MAX_ROUNDS,
        ),
        CodeStep("finalize_cv", finalize_cv),
        Step("letter_writer", "write_letter"),
        Step("interviewer", "prepare_interview"),
        CodeStep("report", write_report),
        *([CodeStep("pdf", make_pdfs)] if with_pdf else []),
    )


class Orchestrator:
    def __init__(
        self,
        provider: Provider,
        run_dir: Path,
        job_text: str,
        cv_text: str,
        ask: AskFn,
        bus: EventBus | None = None,
        registry: Registry | None = None,
        memory: LessonStore | None = None,
        pdf: bool = False,
        resume: tuple[RunState, list[str]] | None = None,
        event_log: str | None = "events.jsonl",
        persist_state: bool = True,
    ) -> None:
        self.provider = provider
        self.registry = registry or Registry()
        self.bus = bus or EventBus()
        if event_log:
            self.bus.subscribe(JsonlSink(run_dir / event_log))
        self.persist_state = persist_state  # the mock interview borrows run_agent but must not touch state.json
        self.ask = ask
        self.memory = memory
        self.pdf = pdf
        self.resumed = resume is not None
        if resume:
            self.state, self.completed = resume
        else:
            self.state = RunState(job_text=job_text, cv_text=cv_text, run_dir=run_dir, lang=self.registry.lang)
            self.completed: list[str] = []
        self.tasks: list[Task] = []
        self.scope = 0  # loop round for checkpoint keys, never restored
        self._lock = threading.RLock()

    @classmethod
    def resume(cls, run_dir: Path, provider: Provider, ask: AskFn, bus: EventBus | None = None,
               memory: LessonStore | None = None, pdf: bool = False) -> "Orchestrator":
        """Rebuilds a run from work/state.json. Raises persist.StateError when it cannot."""
        data = persist.read(run_dir)
        if data.get("status") == "done":
            raise persist.StateError("Bu çalıştırma zaten bitmiş, devam ettirilecek bir şey yok.")
        state, completed = persist.restore(run_dir, data)
        registry = Registry(lang=state.lang)
        return cls(provider, run_dir, state.job_text, state.cv_text, ask, bus, registry, memory, pdf, (state, completed))

    # ---- checkpoints (used by workflow nodes) ----
    def is_done(self, key: str) -> bool:
        return key in self.completed

    def mark(self, key: str) -> None:
        with self._lock:
            if key not in self.completed:
                self.completed.append(key)
            self.save("running")

    def forget(self, key: str) -> None:
        with self._lock:
            if key in self.completed:
                self.completed.remove(key)

    def save(self, status: str, note: str = "") -> None:
        if not self.persist_state:
            return
        with self._lock:
            persist.save(self.state.run_dir, persist.dump(self.state, self.completed, status, self.provider.name, note))

    def _system_prompt(self, card) -> str:
        prompt = card.system_prompt(self.registry.root, self.registry.lang)
        # Preferences come after the contract that holds the no-fabrication rules.
        section = self.memory.prompt_section(card.name, self.registry.lang) if self.memory else ""
        return f"{prompt}\n{section}\n" if section else prompt

    def run_agent(self, agent: str, skill: str) -> None:
        card = self.registry[agent]
        build_prompt, apply = SKILLS[skill]
        task = Task(agent=agent, skill=skill)
        self.tasks.append(task)
        task.state = TaskState.WORKING
        self.bus.publish("task_started", agent, skill=skill, task=task.id, iteration=self.state.iteration)
        request = AgentRequest(
            card=card,
            skill=skill,
            system_prompt=self._system_prompt(card),
            user_prompt=build_prompt(self.state),
            workdir=self.state.run_dir,
            iteration=max(1, self.state.iteration),
        )
        try:
            result = self.provider.run(request)
            apply(self.state, result)
        except RateLimited as e:
            task.state = TaskState.INPUT_REQUIRED
            reason = str(e)
            self.bus.publish("run_paused", agent, skill=skill, task=task.id, reason=reason, run_dir=str(self.state.run_dir))
            self.save("paused", reason)
            raise RunPaused(f"{card.displayName}: {reason}", self.state.run_dir) from e
        except Exception as e:
            error = str(e) if isinstance(e, ProviderError) else f"beklenmeyen hata ({type(e).__name__}: {e})"
            task.state, task.error = TaskState.FAILED, error
            self.bus.publish("task_failed", agent, skill=skill, task=task.id, error=error)
            raise RunFailed(f"{card.displayName}: {error}") from e

        task.messages.append(Message(agent, [TextPart(result.message), DataPart(result.data)]))
        self.state.usage.append({"agent": agent, "skill": skill, **result.usage})
        task.state = TaskState.REJECTED if skill == "verify" and self.state.verdict.get("decision") == "reject" else TaskState.COMPLETED
        self.bus.publish("agent_message", agent, skill=skill, task=task.id, text=result.message, state=task.state.value)
        if skill == "verify" and self.state.verdict.get("overridden"):
            self.bus.publish("warning", "code", text="Doğrulayıcı onay verdi ama kod hataları var: karar 'ret' olarak değiştirildi.")

    def extract_lessons(self) -> None:
        """Best effort: lesson candidates are a bonus, the finished package must not depend on them."""
        if not self.memory or self.is_done("lessons"):
            return
        st = self.state
        try:
            st.saved_lessons = [l.text for l in self.memory.all()]
            self.run_agent("recruiter", "extract_lessons")
            accepted, rejected = screen(st.lesson_candidates, st.job, st.cv_text, self.memory)
        except (RunFailed, RunPaused, MemoryError_) as e:
            self.bus.publish("warning", "code", text=f"Ders adayları çıkarılamadı: {e}")
            return
        st.lesson_candidates, st.lesson_rejected = accepted, rejected
        (st.work / "lesson_candidates.json").write_text(
            json.dumps({"accepted": accepted, "rejected": rejected}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.bus.publish("lessons_proposed", "code", candidates=accepted, rejected=rejected)
        self.mark("lessons")

    def run(self) -> RunState:
        if self.resumed:
            self.bus.publish("run_resumed", provider=self.provider.name, run_dir=str(self.state.run_dir),
                             skipped=len(self.completed))
        else:
            self.bus.publish("run_started", provider=self.provider.name, run_dir=str(self.state.run_dir))
        self.save("running")
        try:
            career_flow(self.pdf).run(self)
        except RunPaused as e:
            self.save("paused", str(e))  # a sibling step may have saved "running" after the pause
            raise
        except RunFailed as e:
            self.save("failed", str(e))
            self.bus.publish("run_failed", error=str(e))
            raise
        except Exception as e:  # a code step (checks, report) crashed
            error = f"beklenmeyen hata ({type(e).__name__}: {e})"
            self.save("failed", error)
            self.bus.publish("run_failed", error=error)
            raise RunFailed(error) from e
        self.extract_lessons()
        self.save("done")
        self.bus.publish("run_finished", converged=self.state.converged, score=self.state.score,
                         output=str(self.state.output))
        return self.state
