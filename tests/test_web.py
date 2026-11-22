"""Web interface: localhost-only guards, uploads, SSE stream and the job-reading gate.
Uses the FastAPI TestClient and the mock provider, so no network and no account."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.inputs import MAX_BYTES
from app.providers.mock import MockProvider
from app.web import server
from conftest import ROOT

BASE = "http://127.0.0.1:8765"
ILAN = (ROOT / "examples" / "ilan.md").read_text(encoding="utf-8")
CV = (ROOT / "examples" / "cv.md").read_text(encoding="utf-8")


class VisionMock(MockProvider):
    """Mock that can also 'read' pictures, standing in for a vision-capable provider."""

    def transcribe(self, media_type, data, kind):
        return ILAN if kind == "ilan" else CV


@pytest.fixture
def client(tmp_path):
    return TestClient(server.create_app(MockProvider(), tmp_path / "runs"), base_url=BASE)


def start(client, **extra):
    data = {"ilan_text": ILAN, "cv_text": CV, "auto_yes": "1", **extra}
    return client.post("/api/runs", data=data)


def wait(client, run_id, until, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        info = client.get(f"/api/runs/{run_id}").json()
        if until(info):
            return info
        time.sleep(0.02)
    raise AssertionError(f"timed out, last state: {info}")


def events(client, run_id):
    body = client.get(f"/api/runs/{run_id}/events").text
    out = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and line != "data: {}":
                out.append(json.loads(line[6:]))
    return out, body


# ---- localhost-only guards --------------------------------------------------------

def test_binds_only_to_loopback(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: seen.update(kw))
    server.serve(MockProvider(), tmp_path, "mock", "tr", 8799, open_browser=False)
    assert seen["host"] == "127.0.0.1" and server.HOST == "127.0.0.1"


def test_other_host_headers_are_refused(client):
    assert client.get("/api/config").status_code == 200
    assert client.get("/api/config", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/config", headers={"Host": "192.168.1.5:8765"}).status_code == 400
    assert client.get("/api/config", headers={"Host": "localhost:8765"}).status_code == 200


def test_cross_site_posts_are_refused(client):
    data = {"ilan_text": ILAN, "cv_text": CV}
    assert client.post("/api/runs", data=data, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/runs", data=data, headers={"Origin": "http://evil.example:8765"}).status_code == 403
    assert client.post("/api/runs", data=data, headers={"Origin": "http://127.0.0.1.evil.example"}).status_code == 403
    assert client.post("/api/runs", data=data, headers={"Origin": BASE, "X": "1"}).status_code == 200


def test_index_config_and_static(client):
    assert "career-crew" in client.get("/").text
    cfg = client.get("/api/config").json()
    assert cfg["mode"] == "mock" and cfg["languages"] == ["tr", "en"] and cfg["max_mb"] == 10
    assert cfg["agents"]["cv_writer"]["color"] == "#4F8EF7"
    assert client.get("/static/app.js").status_code == 200 and client.get("/static/style.css").status_code == 200


# ---- uploads ---------------------------------------------------------------------

def test_upload_validation(client):
    r = client.post("/api/runs", data={"cv_text": CV})
    assert r.status_code == 400 and "İlan eksik" in r.json()["detail"]
    r = client.post("/api/runs", data={"ilan_text": ILAN}, files={"cv_file": ("cv.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400 and "Desteklenmeyen" in r.json()["detail"]
    big = b"a" * (MAX_BYTES + 1)
    r = client.post("/api/runs", data={"ilan_text": ILAN}, files={"cv_file": ("cv.pdf", big, "application/pdf")})
    assert r.status_code == 400 and "çok büyük" in r.json()["detail"]
    r = client.post("/api/runs", data={"ilan_text": ILAN, "cv_text": CV, "lang": "fr"})
    assert r.status_code == 400
    assert client.app.state.manager.runs == {}  # nothing started


def test_file_uploads_run_end_to_end(client):
    files = {"ilan_file": ("ilan.md", ILAN.encode(), "text/markdown"), "cv_file": ("cv.txt", CV.encode(), "text/plain")}
    r = client.post("/api/runs", data={"auto_yes": "1"}, files=files)
    assert r.status_code == 200
    info = wait(client, r.json()["id"], lambda i: i["finished"])
    assert info["status"] == "done"


# ---- run, SSE, files ---------------------------------------------------------------

def test_mock_run_streams_events_and_serves_files(client):
    run_id = start(client).json()["id"]
    wait(client, run_id, lambda i: i["finished"])
    evs, raw = events(client, run_id)
    types = [e["type"] for e in evs]
    assert types[0] == "reading" and "run_started" in types and types[-1] == "run_finished"
    assert raw.rstrip().endswith("event: end\ndata: {}")
    assert [e["id"] for e in evs] == list(range(len(evs)))
    assert types.count("round_recorded") == 2 and types.count("loop_iteration") == 2
    review = next(e for e in evs if e["type"] == "job_review")
    assert review["data"]["auto"] is True and review["data"]["job"]["title"].startswith("Backend")

    # Resuming after an event id returns only later events.
    later, _ = events_after(client, run_id, 5)
    assert [e["id"] for e in later] == list(range(6, len(evs)))

    names = {(f["folder"], f["name"]) for f in client.get(f"/api/runs/{run_id}/files").json()}
    assert {("output", "cv.md"), ("output", "report.md"), ("work", "cv_v1.md"), ("work", "cv_v2.md")} <= names
    cv = client.get(f"/api/runs/{run_id}/files/output/cv.md")
    assert cv.status_code == 200 and "Docker" not in cv.text
    dl = client.get(f"/api/runs/{run_id}/files/output/cv.md?download=1")
    assert "attachment" in dl.headers["content-disposition"]
    assert client.get(f"/api/runs/{run_id}/cv/original").text == CV


def events_after(client, run_id, last_id):
    body = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(last_id)}).text
    out = [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ") and l != "data: {}"]
    return out, body


def test_file_endpoint_blocks_traversal_and_unknown_runs(client):
    run_id = start(client).json()["id"]
    wait(client, run_id, lambda i: i["finished"])
    for path in ("output/..%2F..%2Fevents.jsonl", "output/.env", "secrets/cv.md", "output/nope.md", "..%2Fx/cv.md"):
        assert client.get(f"/api/runs/{run_id}/files/{path}").status_code == 404
    assert client.get("/api/runs/0123456789ab").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc/files").status_code == 404
    # events.jsonl lives in the run folder but is not an exposed folder.
    assert client.get(f"/api/runs/{run_id}/files/run/events.jsonl").status_code == 404


def test_english_run_from_the_web(client):
    run_id = start(client, lang="en").json()["id"]
    assert wait(client, run_id, lambda i: i["finished"])["status"] == "done"


# ---- the job-reading gate -----------------------------------------------------------

def test_gate_waits_for_the_browser_and_accepts_a_correction(client):
    run_id = start(client, auto_yes="0").json()["id"]
    wait(client, run_id, lambda i: i["gate_open"])
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "waiting"

    # One run at a time.
    assert start(client).status_code == 409
    # Bad answers.
    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "x"}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "correct", "text": " "}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/gate", content=b"not json").status_code == 400
    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "correct", "text": "x" * 3000}).status_code == 400

    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "correct", "text": "Seviye senior değil"}).json() == {"ok": True}
    # The analyst runs again and the gate reopens.
    time.sleep(0.05)
    wait(client, run_id, lambda i: i["gate_open"])
    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "approve"}).json() == {"ok": True}
    assert wait(client, run_id, lambda i: i["finished"])["status"] == "done"
    # No question is pending now.
    assert client.post(f"/api/runs/{run_id}/gate", json={"action": "approve"}).status_code == 409

    evs, _ = events(client, run_id)
    types = [e["type"] for e in evs]
    assert types.count("job_review") == 2 and types.count("input_required") == 2
    assert [e["agent"] for e in evs if e["type"] == "task_started"].count("job_analyst") == 2
    state_events = [e for e in evs if e["type"] == "gate_passed"]
    assert len(state_events) == 1


# ---- pictures and failures ----------------------------------------------------------

def test_image_upload_with_mock_fails_with_a_clear_message(client, tmp_path):
    path = tmp_path / "ilan.png"
    Image.new("RGB", (30, 30), "white").save(path)
    files = {"ilan_file": ("ilan.png", path.read_bytes(), "image/png")}
    run_id = client.post("/api/runs", data={"cv_text": CV, "auto_yes": "1"}, files=files).json()["id"]
    wait(client, run_id, lambda i: i["finished"])
    evs, _ = events(client, run_id)
    failed = [e for e in evs if e["type"] == "run_failed"]
    assert failed and "mock modu görsel okuyamaz" in failed[0]["data"]["error"]


def test_image_upload_with_a_vision_provider_runs(tmp_path):
    client = TestClient(server.create_app(VisionMock(), tmp_path / "runs"), base_url=BASE)
    path = tmp_path / "ilan.jpg"
    Image.new("RGB", (30, 30), "white").save(path)
    files = {"ilan_file": ("ilan.jpg", path.read_bytes(), "image/jpeg")}
    run_id = client.post("/api/runs", data={"cv_text": CV, "auto_yes": "1"}, files=files).json()["id"]
    assert wait(client, run_id, lambda i: i["finished"])["status"] == "done"
    run_dir = client.app.state.manager.runs[run_id].run_dir
    assert (run_dir / "inputs" / "ilan.jpg").exists()
    assert "Backend Developer" in (run_dir / "inputs" / "ilan_metin.md").read_text(encoding="utf-8")


# ---- command line ---------------------------------------------------------------------

def test_web_subcommand_starts_the_server(monkeypatch, tmp_path):
    from app import cli

    calls = []
    monkeypatch.setattr("app.web.server.serve", lambda *a, **k: calls.append((a, k)))
    assert cli.main(["web", "--port", "9001", "--dil", "en", "--hizli", "--acma", "--runs", str(tmp_path),
                     "--hafiza", str(tmp_path / "mem")]) == 0
    (args, kwargs), = calls
    assert args[1:] == (tmp_path, "mock", "en", 9001)
    assert kwargs == {"open_browser": False, "memory_dir": tmp_path / "mem"}


def test_web_subcommand_reports_a_busy_port(monkeypatch, capsys):
    from app import cli

    def busy(*a, **k):
        raise OSError("127.0.0.1:9001 kullanımda")

    monkeypatch.setattr("app.web.server.serve", busy)
    assert cli.main(["web", "--port", "9001", "--acma"]) == 2
    assert "kullanımda" in capsys.readouterr().out


def test_web_does_not_offer_a_host_option():
    from app import cli

    with pytest.raises(SystemExit):
        cli.parse_web_args(["--host", "0.0.0.0"])


def test_cli_image_input_with_mock_exits_with_a_message(tmp_path, capsys):
    from app import cli

    img = tmp_path / "ilan.png"
    Image.new("RGB", (30, 30), "white").save(img)
    code = cli.main(["--ilan", str(img), "--cv", str(ROOT / "examples/cv.md"), "--evet", "--hizli", "--runs", str(tmp_path / "r")])
    assert code == 2 and "mock modu görsel okuyamaz" in capsys.readouterr().out


# ---- memory, pause and PDF ---------------------------------------------------------------

@pytest.fixture
def mem_client(tmp_path):
    app = server.create_app(MockProvider(), tmp_path / "runs", memory_dir=tmp_path / "mem")
    return TestClient(app, base_url=BASE)


def test_lessons_need_a_click_and_are_saved_only_when_chosen(mem_client, tmp_path):
    run_id = start(mem_client).json()["id"]
    wait(mem_client, run_id, lambda i: i["finished"])
    got = mem_client.get(f"/api/runs/{run_id}/lessons").json()
    assert len(got["accepted"]) == 2 and len(got["rejected"]) == 1 and not got["answered"]
    assert mem_client.get("/api/lessons").json() == []  # nothing saved by finishing the run
    r = mem_client.post(f"/api/runs/{run_id}/lessons", json={"accept": [0]}, headers={"Origin": BASE})
    assert r.status_code == 200 and len(r.json()["saved"]) == 1
    saved = mem_client.get("/api/lessons").json()
    assert len(saved) == 1 and saved[0]["agent"] == "cv_writer"
    assert mem_client.post(f"/api/runs/{run_id}/lessons", json={"accept": [1]}).status_code == 409
    assert mem_client.delete(f"/api/lessons/{saved[0]['id']}").status_code == 200
    assert mem_client.get("/api/lessons").json() == []
    assert mem_client.delete("/api/lessons/yok").status_code == 404


def test_lesson_answer_validation(mem_client):
    run_id = start(mem_client).json()["id"]
    wait(mem_client, run_id, lambda i: i["finished"])
    assert mem_client.post(f"/api/runs/{run_id}/lessons", json={"accept": [9]}).status_code == 400
    assert mem_client.post(f"/api/runs/{run_id}/lessons", json={"accept": "all"}).status_code == 400
    assert mem_client.post(f"/api/runs/{run_id}/lessons", content=b"x").status_code == 400


def test_cross_origin_cannot_save_lessons(mem_client):
    run_id = start(mem_client).json()["id"]
    wait(mem_client, run_id, lambda i: i["finished"])
    r = mem_client.post(f"/api/runs/{run_id}/lessons", json={"accept": [0]}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403 and mem_client.get("/api/lessons").json() == []


def test_memory_off_by_default(client):
    assert client.get("/api/config").json()["memory"] is False
    assert client.get("/api/lessons").status_code == 404


def test_pdf_option_adds_downloads(client):
    run_id = start(client, pdf="1").json()["id"]
    wait(client, run_id, lambda i: i["finished"])
    names = {f["name"] for f in client.get(f"/api/runs/{run_id}/files").json()}
    assert {"cv.pdf", "cover_letter.pdf"} <= names
    r = client.get(f"/api/runs/{run_id}/files/output/cv.pdf?download=1")
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    run_id = start(client).json()["id"]
    wait(client, run_id, lambda i: i["finished"])
    assert "cv.pdf" not in {f["name"] for f in client.get(f"/api/runs/{run_id}/files").json()}


class LimitOnce(MockProvider):
    def __init__(self):
        super().__init__()
        self.hit = False

    def run(self, request):
        from app.providers.base import RateLimited
        if request.skill == "score" and request.iteration == 2 and not self.hit:
            self.hit = True
            raise RateLimited("limit")
        return super().run(request)


def test_paused_run_can_be_resumed_from_the_browser(tmp_path):
    client = TestClient(server.create_app(LimitOnce(), tmp_path / "runs"), base_url=BASE)
    run_id = start(client).json()["id"]
    info = wait(client, run_id, lambda i: i["finished"])
    assert info["status"] == "paused"
    evs, _ = events(client, run_id)
    assert any(e["type"] == "run_paused" for e in evs)
    (paused,) = client.get("/api/paused").json()
    r = client.post("/api/resume", json={"dir": paused["dir"]}, headers={"Origin": BASE})
    assert r.status_code == 200
    new_id = r.json()["id"]
    info = wait(client, new_id, lambda i: i["finished"])
    assert info["status"] == "done"
    evs, _ = events(client, new_id)
    types = [e["type"] for e in evs]
    assert "run_paused" in types and "run_resumed" in types and types[-1] == "run_finished"  # earlier conversation is replayed
    assert [e["id"] for e in evs] == list(range(len(evs)))
    assert client.get("/api/paused").json() == []
    assert "Deniz" in client.get(f"/api/runs/{new_id}/cv/original").text


def test_resume_rejects_bad_names_and_damaged_state(client, tmp_path):
    assert client.post("/api/resume", json={"dir": "../etc"}).status_code == 400
    assert client.post("/api/resume", json={"dir": "yok"}).status_code == 404
    assert client.post("/api/resume", json={}).status_code == 400
    bad = tmp_path / "runs" / "bozuk" / "work"
    bad.mkdir(parents=True)
    (bad / "state.json").write_text("{x", encoding="utf-8")
    r = client.post("/api/resume", json={"dir": "bozuk"})
    assert r.status_code == 400 and "bozuk" in r.json()["detail"]
    assert client.get("/api/paused").json() == []
