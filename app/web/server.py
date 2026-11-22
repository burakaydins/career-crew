"""Local web interface: FastAPI app that runs the same Orchestrator as the terminal.

Events come from the existing EventBus and reach the browser over SSE. The workflow runs
in a background thread; the job-reading gate (`ask`) blocks that thread until the browser
answers. The server only ever listens on 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import threading
import uuid
import webbrowser
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.events import Event, EventBus
from app.inputs import MAX_BYTES, InputError, check_upload, read_input
from app.orchestrator import Orchestrator, RunFailed, create_run_dir
from app.registry import DEFAULT_LANG, LANGUAGES, Registry

HOST = "127.0.0.1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
STATIC = Path(__file__).parent / "static"
GATE_TIMEOUT_SECONDS = 30 * 60
MAX_TEXT_CHARS = 200_000
MAX_CORRECTION_CHARS = 2_000
RUN_ID = re.compile(r"^[0-9a-f]{12}$")
FILE_NAME = re.compile(r"^[\w.\-]+$")
FILE_FOLDERS = ("output", "work", "inputs")


class LocalOnly:
    """Refuses cross-site writes. A page on another origin can still POST to 127.0.0.1 from the
    user's browser, so a request that carries an Origin header must come from this server itself."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            origin = dict(scope["headers"]).get(b"origin", b"").decode("latin-1")
            if origin:
                m = re.fullmatch(r"http://([^/:]+)(:\d+)?", origin)
                if not m or m.group(1) not in ALLOWED_HOSTS:
                    await JSONResponse({"detail": "Yalnızca bu sayfadan gelen istekler kabul edilir"}, status_code=403)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class Static(StaticFiles):
    """Always revalidate: the files are tiny and change with every release."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


class WebRun:
    """One run as the browser sees it: an event log plus the pending question, if any."""

    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.finished = False
        self.status = "starting"
        self.run_dir: Path | None = None
        self.cv_text = ""
        self.job: dict = {}
        self.gate_open = False
        self.gate_answer: str | None = None
        self.gate_ready = threading.Event()

    def collect(self, event: Event) -> None:
        with self.lock:
            record = asdict(event)
            record["id"] = len(self.events)
            self.events.append(record)
            if event.type == "run_failed":
                self.status = "failed"
            elif event.type == "run_finished":
                self.status = "done"
            elif event.type == "input_required":
                self.status = "waiting"
            elif event.type == "gate_passed" or event.type == "run_started":
                self.status = "running"


class RunManager:
    def __init__(self, runs_dir: Path, provider) -> None:
        self.runs_dir = runs_dir
        self.provider = provider
        self.runs: dict[str, WebRun] = {}
        self.lock = threading.Lock()

    def active(self) -> WebRun | None:
        return next((r for r in self.runs.values() if not r.finished), None)

    def start(self, tmp: Path, files: dict[str, Path], lang: str, auto_yes: bool) -> WebRun:
        with self.lock:
            if self.active():
                raise HTTPException(409, "Zaten çalışan bir süreç var, bitmesini bekleyin")
            run = WebRun(uuid.uuid4().hex[:12])
            self.runs[run.id] = run
        threading.Thread(target=self._work, args=(run, tmp, files, lang, auto_yes), daemon=True).start()
        return run

    def _work(self, run: WebRun, tmp: Path, files: dict[str, Path], lang: str, auto_yes: bool) -> None:
        bus = EventBus()
        bus.subscribe(run.collect)
        try:
            texts = {}
            for kind in ("ilan", "cv"):
                bus.publish("reading", None, kind=kind, name=files[kind].name)
                texts[kind] = read_input(files[kind], self.provider, kind)
            run.cv_text = texts["cv"]
            registry = Registry(lang=lang)
            run_dir = create_run_dir(self.runs_dir, files["ilan"], files["cv"])
            run.run_dir = run_dir
            for kind, f in files.items():
                if f.suffix.lower() != ".md":
                    (run_dir / "inputs" / f"{kind}_metin.md").write_text(texts[kind], encoding="utf-8")
            orch = Orchestrator(
                provider=self.provider, run_dir=run_dir, job_text=texts["ilan"], cv_text=texts["cv"],
                ask=self._make_ask(run, bus, auto_yes), bus=bus, registry=registry,
            )
            orch.run()
        except InputError as e:
            bus.publish("run_failed", None, error=str(e))
        except RunFailed:
            pass  # the orchestrator already published run_failed
        except Exception as e:  # keep the stream from hanging on a bug
            bus.publish("run_failed", None, error=f"beklenmeyen hata ({type(e).__name__}: {e})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with run.lock:
                run.finished = True

    def _make_ask(self, run: WebRun, bus: EventBus, auto_yes: bool):
        def ask(gate: str, state) -> str | None:
            run.job = state.job
            if auto_yes:
                bus.publish("job_review", None, gate=gate, job=state.job, auto=True)
                return None
            run.gate_answer = None
            run.gate_ready.clear()
            run.gate_open = True  # before the event, so a fast click cannot beat it
            bus.publish("job_review", None, gate=gate, job=state.job, auto=False)
            if not run.gate_ready.wait(GATE_TIMEOUT_SECONDS):
                run.gate_open = False
                raise RunFailed("İlan onayı beklenirken zaman aşımı (30 dk)")
            run.gate_open = False
            return run.gate_answer
        return ask


def create_app(provider, runs_dir: Path = Path("runs"), mode: str = "mock", lang: str = DEFAULT_LANG) -> FastAPI:
    manager = RunManager(runs_dir, provider)
    registry = Registry()
    app = FastAPI(title="career-crew", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LocalOnly)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.state.manager = manager

    def get_run(run_id: str) -> WebRun:
        run = manager.runs.get(run_id) if RUN_ID.match(run_id) else None
        if run is None:
            raise HTTPException(404, "Süreç bulunamadı")
        return run

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/config")
    def config():
        return {
            "mode": mode,
            "lang": lang,
            "languages": list(LANGUAGES),
            "max_mb": MAX_BYTES // 1024 // 1024,
            "agents": {n: {"name": c.displayName, "color": c.color, "description": c.description} for n, c in registry.cards.items()},
        }

    @app.post("/api/runs")
    async def create_run(request: Request):
        form = await request.form(max_files=2, max_fields=8)
        run_lang = str(form.get("lang") or lang)
        if run_lang not in LANGUAGES:
            raise HTTPException(400, "Desteklenmeyen dil")
        tmp = Path(tempfile.mkdtemp(prefix="career-crew-"))
        files: dict[str, Path] = {}
        try:
            for kind in ("ilan", "cv"):
                upload = form.get(f"{kind}_file")
                text = str(form.get(f"{kind}_text") or "")
                if isinstance(upload, UploadFile) and upload.filename:
                    data = await upload.read(MAX_BYTES + 1)
                    try:
                        suffix = check_upload(upload.filename, len(data))
                    except InputError as e:
                        raise HTTPException(400, f"{'İlan' if kind == 'ilan' else 'CV'}: {e}") from e
                    path = tmp / f"{kind}{suffix}"
                    path.write_bytes(data)
                elif text.strip():
                    if len(text) > MAX_TEXT_CHARS:
                        raise HTTPException(400, f"{kind}: yapıştırılan metin çok uzun")
                    path = tmp / f"{kind}.md"
                    path.write_text(text, encoding="utf-8")
                else:
                    raise HTTPException(400, f"{'İlan' if kind == 'ilan' else 'CV'} eksik: dosya yükleyin ya da metin yapıştırın")
                files[kind] = path
            run = manager.start(tmp, files, run_lang, str(form.get("auto_yes")) == "1")
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return {"id": run.id}

    @app.get("/api/runs/{run_id}")
    def run_info(run_id: str):
        run = get_run(run_id)
        return {"id": run.id, "status": run.status, "finished": run.finished, "gate_open": run.gate_open, "job": run.job}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = -1):
        run = get_run(run_id)
        last = request.headers.get("last-event-id", "")
        start = int(last) + 1 if last.isdigit() else max(0, after + 1)

        async def stream():
            i, idle = start, 0.0
            while True:
                finished = run.finished
                with run.lock:
                    chunk = run.events[i:]
                for ev in chunk:
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                i += len(chunk)
                if finished and not chunk:
                    yield "event: end\ndata: {}\n\n"
                    return
                if chunk:
                    idle = 0.0
                else:
                    await asyncio.sleep(0.1)
                    idle += 0.1
                    if idle >= 15:
                        yield ": ping\n\n"
                        idle = 0.0

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/runs/{run_id}/gate")
    async def answer_gate(run_id: str, request: Request):
        run = get_run(run_id)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        action = body.get("action") if isinstance(body, dict) else None
        if action not in ("approve", "correct"):
            raise HTTPException(400, "action 'approve' ya da 'correct' olmalı")
        text = str(body.get("text") or "").strip()
        if action == "correct" and not text:
            raise HTTPException(400, "Neyin düzeltileceğini yazın")
        if len(text) > MAX_CORRECTION_CHARS:
            raise HTTPException(400, "Düzeltme metni çok uzun")
        if not run.gate_open:
            raise HTTPException(409, "Şu anda bekleyen bir onay yok")
        run.gate_answer = text if action == "correct" else None
        run.gate_open = False
        run.gate_ready.set()
        return {"ok": True}

    @app.get("/api/runs/{run_id}/cv/original")
    def original_cv(run_id: str):
        return PlainTextResponse(get_run(run_id).cv_text)

    @app.get("/api/runs/{run_id}/files")
    def list_files(run_id: str):
        run = get_run(run_id)
        out = []
        if run.run_dir:
            for folder in FILE_FOLDERS:
                d = run.run_dir / folder
                if d.is_dir():
                    out += [{"folder": folder, "name": f.name, "size": f.stat().st_size}
                            for f in sorted(d.iterdir()) if f.is_file() and FILE_NAME.match(f.name)]
        return out

    @app.get("/api/runs/{run_id}/files/{folder}/{name}")
    def get_file(run_id: str, folder: str, name: str, download: int = 0):
        run = get_run(run_id)
        if folder not in FILE_FOLDERS or not FILE_NAME.match(name) or run.run_dir is None:
            raise HTTPException(404, "Dosya bulunamadı")
        path = (run.run_dir / folder / name).resolve()
        if path.parent != (run.run_dir / folder).resolve() or not path.is_file():
            raise HTTPException(404, "Dosya bulunamadı")
        media = "text/plain; charset=utf-8" if path.suffix in (".md", ".txt", ".json", ".jsonl") else "application/octet-stream"
        headers = {"Content-Disposition": f'attachment; filename="{name}"'} if download else {}
        return FileResponse(path, media_type=media, headers=headers)

    app.mount("/static", Static(directory=STATIC), name="static")
    return app


def serve(provider, runs_dir: Path, mode: str, lang: str, port: int, open_browser: bool = True) -> None:
    import socket

    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex((HOST, port)) == 0:
            raise OSError(f"{HOST}:{port} kullanımda. Başka bir port deneyin: career-crew web --port {port + 1}")
    app = create_app(provider, runs_dir, mode, lang)
    url = f"http://{HOST}:{port}"
    print(f"career-crew web ({mode} modu, yalnızca bu bilgisayardan erişilir): {url}")
    print("Durdurmak için Ctrl+C.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
