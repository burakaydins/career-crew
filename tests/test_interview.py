"""Mock interview: question parsing, the evaluate_answer rules, CLI, web chat and the api provider path.
Runs on the mock provider or a fake client, so no network and no account."""

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import cli, interview
from app.events import EventBus
from app.providers.base import AgentResult, ProviderError
from app.providers.mock import INTERVIEW, MOCK_ANSWERS, MockProvider
from app.skills import RunState, apply_evaluate_answer
from app.web import server
from conftest import ROOT

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def finished_run(tmp_path, capsys):
    assert cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
                     "--runs", str(tmp_path / "runs"), "--hafiza", str(tmp_path / "mem")]) == 0
    capsys.readouterr()
    return next((tmp_path / "runs").iterdir())


# ---- parsing ---------------------------------------------------------------------

def test_parse_headings_with_hints():
    q = interview.parse_questions(INTERVIEW)
    assert len(q) == 8 and q[0].text.startswith("Django'da N+1") and "İpucu" in q[0].hint


def test_parse_numbered_list_fallback_and_nothing():
    q = interview.parse_questions("Giriş\n\n1. **Kendini tanıt**\n   - ipucu burada\n2. Neden biz?\n")
    assert [x.text for x in q] == ["Kendini tanıt", "Neden biz?"] and "ipucu" in q[0].hint
    assert interview.parse_questions("sadece düz metin") == []


# ---- evaluate_answer rules -------------------------------------------------------

def state(lang="tr"):
    s = RunState(job_text="", cv_text="Python ile 3 yıl çalıştım. Testleri %40 artırdım.", run_dir=ROOT, lang=lang)
    s.turn = {"prepared": {"text": "q"}, "asked": "q", "answer": "Raporları 5 saatten 1 saate indirdim."}
    return s


def result(**data):
    return AgentResult(message="Geri bildirim.", data={"verdict": "weak", "flags": [], "framing": "", **data})


def test_numbers_missing_from_the_cv_are_flagged_by_code_even_if_the_model_misses_them():
    s = state()
    apply_evaluate_answer(s, result())
    ev = s.turn["evaluation"]
    assert ev["flags"] == [] and len(ev["code_flags"]) == 2 and "'5'" in ev["code_flags"][0] or "'5'" in ev["code_flags"][1]


def test_a_framing_with_new_numbers_is_withheld():
    s = state()
    apply_evaluate_answer(s, result(flags=[{"claim": "5 saat", "why": "CV'de yok"}], framing="De ki: süreyi 2 saate indirdim."))
    assert "2 saat" not in s.turn["evaluation"]["framing"] and "rakam" in s.turn["evaluation"]["framing"]
    s = state()
    apply_evaluate_answer(s, result(flags=[{"claim": "x", "why": ""}], framing="Testleri %40 artırdığını anlat."))
    assert s.turn["evaluation"]["framing"] == "Testleri %40 artırdığını anlat."


def test_no_framing_without_flags_and_bad_verdict_is_rejected():
    s = state()
    s.turn["answer"] = "Python ile çalıştım."
    apply_evaluate_answer(s, result(framing="Bir şey söyle."))
    assert s.turn["evaluation"]["framing"] == ""
    with pytest.raises(ProviderError):
        apply_evaluate_answer(s, AgentResult(message="x", data={"verdict": "great"}))


# ---- CLI -------------------------------------------------------------------------

def test_cli_scripted_interview_flags_the_invented_numbers_and_writes_feedback(finished_run, capsys):
    before = (finished_run / "work" / "state.json").read_text(encoding="utf-8")
    log_before = (finished_run / "events.jsonl").read_text(encoding="utf-8")
    assert cli.main(["mulakat", str(finished_run), "--betik", "--soru", "4"]) == 0
    out = capsys.readouterr().out
    assert "CV'de yok" in out and "Dürüst çerçeve" in out and "Mülakat bitti" in out
    text = (finished_run / "output" / "mulakat_geri_bildirim.md").read_text(encoding="utf-8")
    assert "## Güçlü cevaplar" in text and "## CV'de olmayan iddialar" in text and "4/4" in text
    # the main run's record is untouched, the interview has its own log
    assert (finished_run / "work" / "state.json").read_text(encoding="utf-8") == before
    assert (finished_run / "events.jsonl").read_text(encoding="utf-8") == log_before
    assert (finished_run / "work" / "interview_events.jsonl").is_file()


def test_cli_interactive_answers_skip_and_early_finish(finished_run, monkeypatch, capsys):
    answers = iter(["Django ile sipariş uygulaması yaptım.", "", "/bitir"])
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: next(answers))
    assert cli.main(["mulakat", str(finished_run), "--soru", "5"]) == 0
    text = (finished_run / "output" / "mulakat_geri_bildirim.md").read_text(encoding="utf-8")
    assert "1/5" in text or "1/5 soru" in text.replace("\n", " ")  # one answered, one skipped, one ended it


def test_cli_nothing_answered_writes_no_file(finished_run, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli.Prompt, "ask", lambda *a, **k: "/bitir")
    assert cli.main(["mulakat", str(finished_run)]) == 0
    assert not (finished_run / "output" / "mulakat_geri_bildirim.md").exists()


def test_cli_errors_are_plain(tmp_path, finished_run, capsys):
    assert cli.main(["mulakat", str(tmp_path / "yok"), "--betik"]) == 2
    assert "bulunamadı" in capsys.readouterr().out
    assert cli.main(["mulakat", str(tmp_path), "--betik"]) == 2  # no state.json
    assert cli.main(["mulakat", str(finished_run), "--soru", "0"]) == 2
    (finished_run / "output" / "interview.md").write_text("soru yok burada", encoding="utf-8")
    assert cli.main(["mulakat", str(finished_run), "--betik"]) == 2
    assert "soru bulunamadı" in capsys.readouterr().out


def test_questions_are_regenerated_when_interview_md_is_missing(finished_run, capsys):
    (finished_run / "output" / "interview.md").unlink()
    assert cli.main(["mulakat", str(finished_run), "--betik", "--soru", "1"]) == 0
    assert (finished_run / "output" / "interview.md").is_file()


def test_limit_stops_the_interview_but_keeps_what_was_answered(finished_run, capsys):
    from app.providers.base import RateLimited

    class Limited(MockProvider):
        def run(self, request):
            if request.skill == "ask_question" and request.iteration == 2:
                raise RateLimited("limit")
            return super().run(request)

    bus = EventBus()
    session = interview.open_session(finished_run, Limited(), bus, 3)
    from app.orchestrator import RunPaused
    with pytest.raises(RunPaused):
        interview.run(session, lambda n, q: MOCK_ANSWERS[n - 1])
    assert "1/3" in (finished_run / "output" / "mulakat_geri_bildirim.md").read_text(encoding="utf-8").replace("\n", " ")
    assert json.loads((finished_run / "work" / "state.json").read_text(encoding="utf-8"))["status"] == "done"


# ---- english, and the api provider path ---------------------------------------------

def test_english_run_gets_english_prompts_and_feedback(tmp_path, capsys):
    cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
              "--dil", "en", "--runs", str(tmp_path / "r"), "--hafiza", str(tmp_path / "m")])
    run_dir = next((tmp_path / "r").iterdir())
    seen = []

    class Spy(MockProvider):
        def run(self, request):
            seen.append(request)
            return super().run(request)

    session = interview.open_session(run_dir, Spy(), EventBus(), 1)
    interview.run(session, lambda n, q: MOCK_ANSWERS[2])
    ask, evaluate = seen
    assert "<prepared_question>" in ask.user_prompt and "Mock interview" in ask.system_prompt
    assert "<candidate_answer>" in evaluate.user_prompt and "<original_cv>" in evaluate.user_prompt
    assert "# Mock interview feedback" in (run_dir / "output" / "mulakat_geri_bildirim.md").read_text(encoding="utf-8")


def test_interview_through_the_api_provider_with_a_fake_client(finished_run, monkeypatch):
    from app.providers.api import ApiProvider
    from test_api_provider import FakeStream, message

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = ApiProvider()
    replies = iter([
        '{"message": "Docker deneyimin var mı?", "data": {"question": "Docker deneyimin var mı?"}, "files": {}}',
        '{"message": "Dürüst cevap.", "data": {"verdict": "strong", "flags": [], "framing": ""}, "files": {}}',
    ])
    calls = []

    def stream(**kw):
        calls.append(kw)
        return FakeStream(message(next(replies)))

    p.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    session = interview.open_session(finished_run, p, EventBus(), 1)
    path = interview.run(session, lambda n, q: "Profesyonel deneyimim yok, öğreniyorum.")
    assert path and len(calls) == 2
    assert "<aday_cevabi>" in json.dumps(calls[1], ensure_ascii=False)


# ---- web -------------------------------------------------------------------------

@pytest.fixture
def client(finished_run):
    return TestClient(server.create_app(MockProvider(), finished_run.parent), base_url=BASE)


def wait(client, run_id, until):
    for _ in range(300):
        info = client.get(f"/api/runs/{run_id}").json()
        if until(info):
            return info
        time.sleep(0.02)
    raise AssertionError(f"timed out: {info}")


def types(client, run_id):
    """Events so far. The SSE endpoint would block until the run ends, so read the collected list."""
    return list(client.app.state.manager.runs[run_id].events)


def test_web_interview_chat_flow(client, finished_run):
    cfg = client.get("/api/config").json()
    assert cfg["mock_answers"] == MOCK_ANSWERS
    run_id = client.post("/api/interviews", json={"dir": finished_run.name, "count": 3}).json()["id"]
    wait(client, run_id, lambda i: i["status"] == "waiting")
    assert client.post(f"/api/runs/{run_id}/answer", json={"action": "answer", "text": ""}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/answer", json={"action": "answer", "text": MOCK_ANSWERS[0]}).status_code == 200
    for _ in range(300):  # wait for the next question
        if sum(e["type"] == "input_required" for e in types(client, run_id)) == 2:
            break
        time.sleep(0.02)
    client.post(f"/api/runs/{run_id}/answer", json={"action": "skip"})
    for _ in range(300):
        if sum(e["type"] == "input_required" for e in types(client, run_id)) == 3:
            break
        time.sleep(0.02)
    client.post(f"/api/runs/{run_id}/answer", json={"action": "finish"})
    wait(client, run_id, lambda i: i["finished"])
    assert client.post(f"/api/runs/{run_id}/answer", json={"action": "answer", "text": "x"}).status_code == 409
    got = types(client, run_id)
    kinds = [e["type"] for e in got]
    assert kinds.count("interview_question") == 3 and kinds.count("interview_evaluation") == 1
    assert "interview_report" in kinds
    report = client.get(f"/api/runs/{run_id}/files/output/mulakat_geri_bildirim.md")
    assert report.status_code == 200 and "1/3" in report.text.replace("\n", " ")


def test_web_interview_rejects_bad_input_and_blocks_a_second_run(client, finished_run):
    assert client.post("/api/interviews", json={"dir": "../x", "count": 3}).status_code == 400
    assert client.post("/api/interviews", json={"dir": finished_run.name, "count": 99}).status_code == 400
    assert client.post("/api/interviews", json={"dir": "yok", "count": 3}).status_code == 400
    first = client.post("/api/interviews", json={"dir": finished_run.name, "count": 2})
    assert first.status_code == 200
    assert client.post("/api/interviews", json={"dir": finished_run.name, "count": 2}).status_code == 409
    client.post(f"/api/runs/{first.json()['id']}/answer", json={"action": "finish"})
