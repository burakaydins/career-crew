"""Runs the career workflow: wires agents, checks, the event bus and the run folder."""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path
from typing import Callable

from app import report as report_mod
from app.checks import run_all
from app.events import EventBus, JsonlSink
from app.providers.base import AgentRequest, Provider, ProviderError
from app.registry import Registry
from app.skills import SKILLS, RunState
from app.tasks import DataPart, Message, Task, TaskState, TextPart
from app.workflow import CodeStep, Loop, Parallel, Sequential, Step, UserGate

TARGET_SCORE = 80
MAX_ROUNDS = 3

AskFn = Callable[[str, RunState], "str | None"]


class RunFailed(RuntimeError):
    pass


def slugify(text: str) -> str:
    text = text.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "run"


def create_run_dir(base: Path, job_file: Path, cv_file: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = base / f"{stamp}_{slugify(job_file.stem)}"
    for sub in ("inputs", "work", "output"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
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


def career_flow() -> Sequential:
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
    ) -> None:
        self.provider = provider
        self.registry = registry or Registry()
        self.bus = bus or EventBus()
        self.bus.subscribe(JsonlSink(run_dir / "events.jsonl"))
        self.ask = ask
        self.state = RunState(job_text=job_text, cv_text=cv_text, run_dir=run_dir, lang=self.registry.lang)
        self.tasks: list[Task] = []

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
            system_prompt=card.system_prompt(self.registry.root, self.registry.lang),
            user_prompt=build_prompt(self.state),
            workdir=self.state.run_dir,
            iteration=max(1, self.state.iteration),
        )
        try:
            result = self.provider.run(request)
            apply(self.state, result)
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

    def run(self) -> RunState:
        self.bus.publish("run_started", provider=self.provider.name, run_dir=str(self.state.run_dir))
        try:
            career_flow().run(self)
        except RunFailed as e:
            self.bus.publish("run_failed", error=str(e))
            raise
        except Exception as e:  # a code step (checks, report) crashed
            error = f"beklenmeyen hata ({type(e).__name__}: {e})"
            self.bus.publish("run_failed", error=error)
            raise RunFailed(error) from e
        self.bus.publish("run_finished", converged=self.state.converged, score=self.state.score,
                         output=str(self.state.output))
        return self.state
