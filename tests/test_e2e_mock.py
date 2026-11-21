import json

from app.cli import main
from app.events import EventBus
from app.orchestrator import Orchestrator, create_run_dir
from app.providers.base import AgentResult
from app.providers.mock import MockProvider
from conftest import ROOT


def test_cli_mock_end_to_end(tmp_path):
    code = main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"),
                 "--evet", "--hizli", "--runs", str(tmp_path)])
    assert code == 0
    (run,) = tmp_path.iterdir()
    for f in ("cv.md", "cover_letter.md", "interview.md", "report.md"):
        assert (run / "output" / f).read_text(encoding="utf-8").strip()
    assert (run / "inputs" / "cv.md").exists() and (run / "work" / "job.json").exists()
    events = [json.loads(l)["type"] for l in (run / "events.jsonl").read_text().splitlines()]
    assert events[0] == "run_started" and events[-1] == "run_finished"
    assert events.count("loop_iteration") == 2
    assert "Docker" not in (run / "output" / "cv.md").read_text(encoding="utf-8")


class StubbornProvider(MockProvider):
    """Always returns round 1 (fabricated) and a verifier that wrongly approves."""

    def run(self, request):
        request.iteration = 1
        result = super().run(request)
        if request.skill == "verify":
            return AgentResult(message="Onay.", data={"decision": "approve", "issues": []})
        return result


def test_verifier_cannot_override_code_errors_and_loop_gives_up(tmp_path, example_cv, example_job_text):
    run_dir = create_run_dir(tmp_path, ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
    seen = []
    bus = EventBus()
    bus.subscribe(lambda e: seen.append(e))
    state = Orchestrator(StubbornProvider(), run_dir, example_job_text, example_cv,
                         ask=lambda g, s: None, bus=bus).run()
    assert len(state.rounds) == 3
    assert not state.converged
    assert state.verdict["decision"] == "reject" and state.verdict["overridden"]
    assert any(e.type == "warning" and "hedefe ulaşılamadı" in e.data["text"] for e in seen)
    assert "hedefe ulaşmadı" in (run_dir / "output" / "report.md").read_text(encoding="utf-8")


class CrashingProvider(MockProvider):
    def run(self, request):
        if request.skill == "score":
            raise KeyError("boom")
        return super().run(request)


def test_unexpected_error_stops_cleanly(tmp_path, example_cv, example_job_text):
    import pytest
    from app.orchestrator import RunFailed

    run_dir = create_run_dir(tmp_path, ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
    with pytest.raises(RunFailed, match="beklenmeyen hata"):
        Orchestrator(CrashingProvider(), run_dir, example_job_text, example_cv, ask=lambda g, s: None).run()
    events = [json.loads(l)["type"] for l in (run_dir / "events.jsonl").read_text().splitlines()]
    assert "task_failed" in events and events[-1] == "run_failed"


class PlateauProvider(MockProvider):
    """Clean CV every round, but the score never reaches 80 (real gaps)."""

    def run(self, request):
        request.iteration = 2  # the clean round of the script
        result = super().run(request)
        if request.skill == "score":
            return AgentResult(message="Puan 62.", data={"score": 62, "missing": ["Docker yok"]})
        return result


def test_plateau_stops_after_two_clean_rounds(tmp_path, example_cv, example_job_text):
    run_dir = create_run_dir(tmp_path, ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
    seen = []
    bus = EventBus()
    bus.subscribe(lambda e: seen.append(e))
    state = Orchestrator(PlateauProvider(), run_dir, example_job_text, example_cv,
                         ask=lambda g, s: None, bus=bus).run()
    assert len(state.rounds) == 2
    assert state.plateau and not state.converged
    done = next(e for e in seen if e.type == "loop_done")
    assert done.data["stopped_early"] is True
    assert "erken durduruldu" in (run_dir / "output" / "report.md").read_text(encoding="utf-8")
