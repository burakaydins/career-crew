"""Replay: same events, same Renderer, timing cut down, clear errors for broken logs."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app import cli, replay
from app.events import Event
from app.providers.mock import MockProvider
from app.web import server
from conftest import ROOT

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def finished_run(tmp_path, capsys):
    code = cli.main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli",
                     "--runs", str(tmp_path / "runs"), "--hafiza", str(tmp_path / "mem")])
    assert code == 0
    capsys.readouterr()
    return next((tmp_path / "runs").iterdir())


def ev(ts, type="agent_message"):
    return Event(type=type, agent="cv_writer", data={"text": "x"}, ts=ts)


# ---- timing ----------------------------------------------------------------------

def test_long_gaps_are_cut_and_speed_scales_the_rest():
    events = [ev(100.0), ev(100.5), ev(400.0)]
    assert replay.delays(events) == [0.0, 0.5, replay.MAX_GAP]
    fast = replay.delays(events, speed=2)
    assert fast[1] == pytest.approx(0.25) and fast[2] == pytest.approx(replay.MAX_GAP / 2)


def test_tiny_gaps_keep_a_minimum_so_messages_do_not_blur():
    assert replay.delays([ev(1.0), ev(1.0)])[1] == replay.MIN_GAP


def test_instant_never_sleeps():
    slept = []
    list(replay.play([ev(1.0), ev(50.0)], lambda e: None, instant=True, sleep=slept.append))
    assert slept == []
    list(replay.play([ev(1.0), ev(50.0)], lambda e: None, sleep=slept.append))
    assert slept == [replay.MAX_GAP]


# ---- loading ---------------------------------------------------------------------

def test_missing_folder_and_missing_log(tmp_path):
    with pytest.raises(replay.ReplayError, match="bulunamadı"):
        replay.load_events(tmp_path / "yok")
    with pytest.raises(replay.ReplayError, match="events.jsonl yok"):
        replay.load_events(tmp_path)


def test_broken_and_empty_logs(tmp_path):
    (tmp_path / "events.jsonl").write_text('{"type": "run_started", "ts": 1}\n{oops\n', encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="satır 2"):
        replay.load_events(tmp_path)
    (tmp_path / "events.jsonl").write_text('{"type": "x"}\n', encoding="utf-8")  # no timestamp
    with pytest.raises(replay.ReplayError, match="bozuk"):
        replay.load_events(tmp_path)
    (tmp_path / "events.jsonl").write_text("\n", encoding="utf-8")
    with pytest.raises(replay.ReplayError, match="boş"):
        replay.load_events(tmp_path)


# ---- terminal --------------------------------------------------------------------

def test_cli_replay_prints_what_the_live_run_printed(finished_run, capsys):
    code = cli.main(["replay", str(finished_run), "--aninda"])
    out = capsys.readouterr().out
    assert code == 0
    assert "CV turu 1/3" in out and "Kod kontrolü" in out and "Bitti" in out and "cv.md" in out


def test_cli_replay_works_when_the_run_was_moved(finished_run, tmp_path, capsys):
    import shutil
    moved = tmp_path / "elsewhere"
    shutil.copytree(finished_run, moved)
    shutil.rmtree(finished_run)  # the absolute output path in the log no longer exists
    assert cli.main(["replay", str(moved), "--aninda"]) == 0
    assert "Bitti" in capsys.readouterr().out


def test_cli_replay_errors_are_plain(tmp_path, capsys):
    assert cli.main(["replay", str(tmp_path / "yok")]) == 2
    assert "bulunamadı" in capsys.readouterr().out
    (tmp_path / "events.jsonl").write_text("{oops", encoding="utf-8")
    assert cli.main(["replay", str(tmp_path)]) == 2
    assert "bozuk" in capsys.readouterr().out
    assert cli.main(["replay", str(tmp_path), "--hiz", "0"]) == 2


# ---- web -------------------------------------------------------------------------

@pytest.fixture
def client(finished_run):
    return TestClient(server.create_app(MockProvider(), finished_run.parent), base_url=BASE)


def stream(client, run_id):
    body = client.get(f"/api/runs/{run_id}/events").text
    return [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ") and l != "data: {}"]


def wait_finished(client, run_id):
    for _ in range(300):
        if client.get(f"/api/runs/{run_id}").json()["finished"]:
            return
        time.sleep(0.02)
    raise AssertionError("replay did not finish")


def test_history_lists_past_runs(client, finished_run):
    items = client.get("/api/history").json()
    assert [i["dir"] for i in items] == [finished_run.name]
    assert items[0]["status"] == "done" and items[0]["title"] and items[0]["interview"] is True


def test_web_replay_streams_the_recorded_events(client, finished_run):
    original = [json.loads(l) for l in (finished_run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    run_id = client.post("/api/replay", json={"dir": finished_run.name, "instant": True}).json()["id"]
    wait_finished(client, run_id)
    got = stream(client, run_id)
    assert [e["type"] for e in got] == [e["type"] for e in original]
    assert all(e["data"].get("auto") for e in got if e["type"] == "job_review")
    assert client.get(f"/api/runs/{run_id}/cv/original").text.startswith("# ")
    assert client.get(f"/api/runs/{run_id}/files/output/cv.md").status_code == 200


def test_web_replay_upto_stops_after_n_events(client, finished_run):
    run_id = client.post("/api/replay", json={"dir": finished_run.name, "upto": 4}).json()["id"]
    wait_finished(client, run_id)
    assert len(stream(client, run_id)) == 4


def test_replay_does_not_block_a_live_run_and_rejects_bad_input(client, finished_run):
    client.post("/api/replay", json={"dir": finished_run.name, "speed": 0.1})  # slow on purpose, still playing
    r = client.post("/api/runs", data={"ilan_text": "x" * 20, "cv_text": "y" * 20, "auto_yes": "1"})
    assert r.status_code == 200
    assert client.post("/api/replay", json={"dir": "../etc"}).status_code == 400
    assert client.post("/api/replay", json={"dir": "yok"}).status_code == 404
    assert client.post("/api/replay", json={"dir": finished_run.name, "speed": 0}).status_code == 400
    assert client.post("/api/replay", json={"dir": finished_run.name, "upto": "3"}).status_code == 400
    assert client.post("/api/replay", json={}).status_code == 400


def test_a_long_list_of_code_findings_is_folded_in_the_terminal(capsys):
    from app.cli import Renderer
    from app.registry import Registry
    errs = [f"sorun {i}" for i in range(9)]
    r = Renderer(Registry())
    r(Event("checks", "code", {"errors": errs, "warnings": [], "ats_before": 1, "ats_after": 2}))
    out = capsys.readouterr().out
    assert "9 sorun" in out and "sorun 2" in out and "sorun 3" not in out and "6 sorun daha" in out
    r(Event("checks", "code", {"errors": errs[:5], "warnings": [], "ats_before": 1, "ats_after": 2}))
    assert "sorun 4" in capsys.readouterr().out  # a short list is shown in full
