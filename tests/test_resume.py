"""Pause on a usage limit and continue where the run stopped."""

import json
import subprocess

import pytest

from app import cli, persist
from app.events import EventBus
from app.orchestrator import Orchestrator, RunPaused, create_run_dir
from app.providers.base import RateLimited, ProviderError, looks_like_limit
from app.providers.mock import MockProvider
from conftest import ROOT

ILAN = (ROOT / "examples/ilan.md").read_text(encoding="utf-8")
CV = (ROOT / "examples/cv.md").read_text(encoding="utf-8")


class Counting(MockProvider):
    """Records every call; raises RateLimited the first time (skill, iteration) comes up."""

    def __init__(self, limit_at=None):
        super().__init__()
        self.limit_at, self.calls = limit_at, []

    def run(self, request):
        key = (request.skill, request.iteration)
        if self.limit_at == key:
            self.limit_at = None
            raise RateLimited("kullanım limiti doldu")
        self.calls.append(key)
        return super().run(request)


def new_run(tmp_path):
    return create_run_dir(tmp_path / "runs", ROOT / "examples/ilan.md", ROOT / "examples/cv.md")


def events_of(run_dir):
    return [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("limit_at", [("analyze_job", 1), ("tailor_cv", 2), ("score", 2), ("write_letter", 2)])
def test_pause_then_resume_matches_an_uninterrupted_run(tmp_path, limit_at):
    whole = new_run(tmp_path / "a")
    Orchestrator(Counting(), whole, ILAN, CV, ask=lambda g, s: None).run()

    run_dir = new_run(tmp_path / "b")
    first = Counting(limit_at)
    with pytest.raises(RunPaused) as info:
        Orchestrator(first, run_dir, ILAN, CV, ask=lambda g, s: None).run()
    assert info.value.run_dir == run_dir
    types = [e["type"] for e in events_of(run_dir)]
    assert "run_paused" in types and "run_failed" not in types
    data = persist.read(run_dir)
    assert data["status"] == "paused"

    second = Counting()
    orch = Orchestrator.resume(run_dir, second, ask=lambda g, s: None)
    orch.run()
    # Nothing that finished before the pause is paid for twice.
    # Only the call that hit the limit and what comes after it runs again.
    assert second.calls[0] == limit_at
    assert not set(first.calls) & set(second.calls)
    for name in ("cv.md", "cover_letter.md", "interview.md"):
        assert (run_dir / "output" / name).read_text() == (whole / "output" / name).read_text()
    assert persist.read(run_dir)["status"] == "done"
    assert [e["type"] for e in events_of(run_dir)].count("run_resumed") == 1
    assert len(orch.state.rounds) == 2


def test_resume_keeps_the_cv_loop_round_and_best_round(tmp_path):
    run_dir = new_run(tmp_path)
    with pytest.raises(RunPaused):
        Orchestrator(Counting(("tailor_cv", 2)), run_dir, ILAN, CV, ask=lambda g, s: None).run()
    orch = Orchestrator.resume(run_dir, Counting(), ask=lambda g, s: None)
    assert orch.state.iteration == 2 and len(orch.state.rounds) == 1 and orch.state.best is orch.state.rounds[0]
    state = orch.run()
    assert len(state.rounds) == 2 and state.converged and state.best is state.rounds[1]


def test_gate_is_not_asked_again_after_it_passed(tmp_path):
    run_dir = new_run(tmp_path)
    asked = []
    with pytest.raises(RunPaused):
        Orchestrator(Counting(("tailor_cv", 1)), run_dir, ILAN, CV, ask=lambda g, s: asked.append(g)).run()
    Orchestrator.resume(run_dir, Counting(), ask=lambda g, s: asked.append(g)).run()
    assert asked == ["confirm_job"]


def test_pause_during_gate_correction_reruns_analysis(tmp_path):
    run_dir = new_run(tmp_path)
    answers = iter(["Seviye senior olmalı", None])
    p1 = Counting(("analyze_job", 1))
    # first analysis passes, the user corrects, the rerun hits the limit
    p1.limit_at = None

    class LimitOnSecond(Counting):
        n = 0

        def run(self, request):
            if request.skill == "analyze_job":
                LimitOnSecond.n += 1
                if LimitOnSecond.n == 2:
                    raise RateLimited("limit")
            return super().run(request)

    with pytest.raises(RunPaused):
        Orchestrator(LimitOnSecond(), run_dir, ILAN, CV, ask=lambda g, s: next(answers)).run()
    p = Counting()
    Orchestrator.resume(run_dir, p, ask=lambda g, s: None).run()
    assert p.calls[0][0] == "analyze_job"  # the correction rerun was not skipped


def test_hard_failure_is_resumable_too(tmp_path):
    class Boom(Counting):
        def run(self, request):
            if request.skill == "write_letter":
                raise ProviderError("kötü yanıt")
            return super().run(request)

    run_dir = new_run(tmp_path)
    with pytest.raises(Exception):
        Orchestrator(Boom(), run_dir, ILAN, CV, ask=lambda g, s: None).run()
    assert persist.read(run_dir)["status"] == "failed"
    Orchestrator.resume(run_dir, Counting(), ask=lambda g, s: None).run()
    assert (run_dir / "output" / "interview.md").exists()


# ---- damaged state ------------------------------------------------------------------------

def test_missing_corrupt_and_foreign_state(tmp_path):
    run_dir = new_run(tmp_path)
    with pytest.raises(persist.StateError, match="Durum dosyası yok"):
        Orchestrator.resume(run_dir, MockProvider(), ask=lambda g, s: None)
    state = run_dir / "work" / "state.json"
    state.write_text("{yarım", encoding="utf-8")
    with pytest.raises(persist.StateError, match="bozuk"):
        Orchestrator.resume(run_dir, MockProvider(), ask=lambda g, s: None)
    state.write_text(json.dumps({"version": 99, "state": {}, "completed": []}), encoding="utf-8")
    with pytest.raises(persist.StateError, match="uyumsuz"):
        Orchestrator.resume(run_dir, MockProvider(), ask=lambda g, s: None)
    state.write_text(json.dumps({"version": 1, "status": "paused", "state": {"job_text": "x"}, "completed": []}), encoding="utf-8")
    with pytest.raises(persist.StateError, match="bozuk"):
        Orchestrator.resume(run_dir, MockProvider(), ask=lambda g, s: None)


def test_finished_run_cannot_be_resumed(tmp_path):
    run_dir = new_run(tmp_path)
    Orchestrator(Counting(), run_dir, ILAN, CV, ask=lambda g, s: None).run()
    with pytest.raises(persist.StateError, match="zaten bitmiş"):
        Orchestrator.resume(run_dir, MockProvider(), ask=lambda g, s: None)


# ---- terminal -------------------------------------------------------------------------------

def test_cli_pauses_with_clean_exit_code_and_resumes(tmp_path, monkeypatch, capsys):
    limit = Counting(("score", 1))
    monkeypatch.setattr(cli, "make_provider", lambda mode, delay: limit)
    base = ["--hafiza", str(tmp_path / "mem"), "--runs", str(tmp_path / "runs"), "--evet", "--hizli"]
    code = cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), *base])
    out = capsys.readouterr().out
    assert code == cli.EXIT_PAUSED == 75
    (run_dir,) = (tmp_path / "runs").iterdir()
    assert f"career-crew --devam {run_dir}" in out.replace("\n", "")
    assert not (run_dir / "output" / "report.md").exists()

    monkeypatch.setattr(cli, "make_provider", lambda mode, delay: Counting())
    assert cli.main(["--devam", str(run_dir), *base]) == 0
    assert (run_dir / "output" / "report.md").exists()


def test_cli_resume_errors(tmp_path, capsys):
    assert cli.main(["--devam", str(tmp_path / "yok"), "--hafiza", str(tmp_path / "m")]) == 2
    (tmp_path / "r" / "work").mkdir(parents=True)
    (tmp_path / "r" / "work" / "state.json").write_text("[]", encoding="utf-8")
    assert cli.main(["--devam", str(tmp_path / "r"), "--hafiza", str(tmp_path / "m")]) == 2
    assert "uyumsuz" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["--hafiza", str(tmp_path / "m")])  # neither --devam nor --ilan/--cv


# ---- limit detection -------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Claude AI usage limit reached|1760000000", True),
    ("You've hit your limit · resets 3pm", True),
    ("429 Too Many Requests", True),
    ("rate_limit_error", True),
    ("Invalid API key", False),
    ("Yanıtta JSON bulunamadı", False),
])
def test_looks_like_limit(text, expected):
    assert looks_like_limit(text) is expected


def fake_claude(monkeypatch, result_text, is_error=True):
    from app.providers.claude_code import ClaudeCodeProvider

    line = json.dumps({"type": "result", "is_error": is_error, "result": result_text})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout=line + "\n", stderr=""))
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    return ClaudeCodeProvider()


def test_claude_code_limit_message_becomes_rate_limited(monkeypatch):
    p = fake_claude(monkeypatch, "Claude AI usage limit reached|1760000000")
    with pytest.raises(RateLimited):
        p._invoke(["claude"], "x", ".")
    p = fake_claude(monkeypatch, "Invalid API key")
    with pytest.raises(ProviderError) as e:
        p._invoke(["claude"], "x", ".")
    assert not isinstance(e.value, RateLimited)


def test_claude_code_limit_without_result_line(monkeypatch):
    from app.providers.claude_code import ClaudeCodeProvider

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="Error: usage limit reached"))
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    with pytest.raises(RateLimited):
        ClaudeCodeProvider()._invoke(["claude"], "x", ".")
