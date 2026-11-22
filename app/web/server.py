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
from app import interview as interview_mod, persist, replay as replay_mod
from app.memory import LessonStore, MemoryError_
from app.orchestrator import Orchestrator, RunFailed, RunPaused, create_run_dir
from app.providers.mock import MOCK_ANSWERS
from app.registry import DEFAULT_LANG, LANGUAGES, Registry

HOST = "127.0.0.1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
STATIC = Path(__file__).parent / "static"
GATE_TIMEOUT_SECONDS = 30 * 60
MAX_TEXT_CHARS = 200_000
MAX_CORRECTION_CHARS = 2_000
RUN_ID = re.compile(r"^[0-9a-f]{12}$")
FILE_NAME = re.compile(r"^[\w.\-]+$")
RUN_DIR_NAME = re.compile(r"^[\w.\-]+$")
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
        self.lessons_answered = False
        self.replay = False
        self.answer_open = False
        self.answer: str | None = None
        self.answer_ready = threading.Event()

    def collect(self, event: Event) -> None:
        with self.lock:
            record = asdict(event)
            record["id"] = len(self.events)
            self.events.append(record)
            if event.type == "run_failed":
                self.status = "failed"
            elif event.type == "run_finished":
                self.status = "done"
            elif event.type == "run_paused":
                self.status = "paused"
            elif event.type == "run_resumed":
                self.status = "running"
            elif event.type == "input_required":
                self.status = "waiting"
            elif event.type == "gate_passed" or event.type == "run_started":
                self.status = "running"


class RunManager:
    def __init__(self, runs_dir: Path, provider, memory: LessonStore | None = None) -> None:
        self.runs_dir = runs_dir
        self.provider = provider
        self.memory = memory
        self.runs: dict[str, WebRun] = {}
        self.lock = threading.Lock()

    def active(self) -> WebRun | None:
        return next((r for r in self.runs.values() if not r.finished and not r.replay), None)

    def start(self, tmp: Path, files: dict[str, Path], lang: str, auto_yes: bool, pdf: bool = False) -> WebRun:
        with self.lock:
            if self.active():
                raise HTTPException(409, "Zaten çalışan bir süreç var, bitmesini bekleyin")
            run = WebRun(uuid.uuid4().hex[:12])
            self.runs[run.id] = run
        threading.Thread(target=self._work, args=(run, tmp, files, lang, auto_yes, pdf), daemon=True).start()
        return run

    def _work(self, run: WebRun, tmp: Path, files: dict[str, Path], lang: str, auto_yes: bool, pdf: bool = False) -> None:
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
                memory=self.memory, pdf=pdf,
            )
            orch.run()
        except InputError as e:
            bus.publish("run_failed", None, error=str(e))
        except (RunFailed, RunPaused):
            pass  # the orchestrator already published run_failed / run_paused
        except Exception as e:  # keep the stream from hanging on a bug
            bus.publish("run_failed", None, error=f"beklenmeyen hata ({type(e).__name__}: {e})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with run.lock:
                run.finished = True

    def history(self, limit: int = 50) -> list[dict]:
        """Past runs that can be replayed (they have an events.jsonl)."""
        out = []
        if self.runs_dir.is_dir():
            for d in sorted(self.runs_dir.iterdir(), reverse=True):
                if not (d / "events.jsonl").is_file() or not RUN_DIR_NAME.match(d.name):
                    continue
                try:
                    data = persist.read(d)
                    title, status = data["state"].get("job", {}).get("title", ""), data.get("status", "")
                except persist.StateError:
                    title, status = "", ""
                out.append({"dir": d.name, "title": title, "status": status,
                            "interview": (d / "output" / "interview.md").is_file() or status == "done"})
                if len(out) >= limit:
                    break
        return out

    def start_replay(self, name: str, speed: float, instant: bool, upto: int | None) -> WebRun:
        if not RUN_DIR_NAME.match(name) or name in (".", ".."):
            raise HTTPException(400, "Geçersiz klasör adı")
        run_dir = self.runs_dir / name
        try:
            events = replay_mod.load_events(run_dir)
        except replay_mod.ReplayError as e:
            raise HTTPException(404 if not run_dir.is_dir() else 400, str(e)) from e
        if upto is not None:
            events, instant = events[:max(0, upto)], True
        for e in events:
            if e.type == "job_review":
                e.data["auto"] = True  # the gate was answered long ago, nothing to click
        run = WebRun(uuid.uuid4().hex[:12])
        run.replay, run.run_dir = True, run_dir
        try:
            state = persist.read(run_dir)["state"]
            run.cv_text, run.job = state.get("cv_text", ""), state.get("job", {})
        except persist.StateError:
            cv = next(iter(sorted((run_dir / "inputs").glob("cv.*"))), None) if (run_dir / "inputs").is_dir() else None
            run.cv_text = cv.read_text(encoding="utf-8", errors="replace") if cv and cv.suffix in (".md", ".txt") else ""
        with self.lock:
            self.runs[run.id] = run
        threading.Thread(target=self._play, args=(run, events, speed, instant), daemon=True).start()
        return run

    def _play(self, run: WebRun, events: list[Event], speed: float, instant: bool) -> None:
        try:
            for _ in replay_mod.play(events, run.collect, speed, instant):
                pass
        finally:
            with run.lock:
                run.finished = True

    def start_interview(self, name: str, count: int) -> WebRun:
        if not RUN_DIR_NAME.match(name) or name in (".", ".."):
            raise HTTPException(400, "Geçersiz klasör adı")
        with self.lock:
            if self.active():
                raise HTTPException(409, "Zaten çalışan bir süreç var, bitmesini bekleyin")
            run = WebRun(uuid.uuid4().hex[:12])
            run.run_dir = self.runs_dir / name
            bus = EventBus()
            bus.subscribe(run.collect)
            try:
                session = interview_mod.open_session(run.run_dir, self.provider, bus, count)
            except interview_mod.InterviewError as e:
                raise HTTPException(400, str(e)) from e
            except RunFailed as e:
                raise HTTPException(500, str(e)) from e
            run.job = session.state.job
            self.runs[run.id] = run
        threading.Thread(target=self._work_interview, args=(run, session, bus), daemon=True).start()
        return run

    def _work_interview(self, run: WebRun, session, bus: EventBus) -> None:
        def get_answer(n: int, question: str) -> str | None:
            run.answer, run.answer_open = None, True  # before the event, so a fast click cannot beat it
            run.answer_ready.clear()
            bus.publish("input_required", None, kind="answer", n=n)
            if not run.answer_ready.wait(GATE_TIMEOUT_SECONDS):
                run.answer_open = False
                return None
            return run.answer

        try:
            interview_mod.run(session, get_answer)
        except RunPaused as e:
            bus.publish("run_paused", "interviewer", reason=str(e), run_dir=str(run.run_dir))
        except RunFailed as e:
            bus.publish("run_failed", None, error=str(e))
        except Exception as e:
            bus.publish("run_failed", None, error=f"beklenmeyen hata ({type(e).__name__}: {e})")
        finally:
            with run.lock:
                run.finished = True

    def paused(self) -> list[dict]:
        out = []
        if self.runs_dir.is_dir():
            for d in sorted(self.runs_dir.iterdir(), reverse=True):
                try:
                    data = persist.read(d)
                except persist.StateError:
                    continue
                if data.get("status") == "paused":
                    out.append({"dir": d.name, "title": data["state"].get("job", {}).get("title", ""), "note": data.get("note", "")})
        return out

    def resume(self, name: str, pdf: bool = False) -> WebRun:
        if not RUN_DIR_NAME.match(name) or name in (".", ".."):
            raise HTTPException(400, "Geçersiz klasör adı")
        run_dir = self.runs_dir / name
        if not run_dir.is_dir():
            raise HTTPException(404, "Çalıştırma klasörü bulunamadı")
        bus = EventBus()
        run = WebRun(uuid.uuid4().hex[:12])
        bus.subscribe(run.collect)
        try:
            orch = Orchestrator.resume(run_dir, self.provider, self._make_ask(run, bus, False), bus, memory=self.memory, pdf=pdf)
        except persist.StateError as e:
            raise HTTPException(400, str(e)) from e
        # Show the earlier conversation again, then continue it.
        log = run_dir / "events.jsonl"
        if log.is_file():
            for line in log.read_text(encoding="utf-8").splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                ev["id"] = len(run.events)
                run.events.append(ev)
        run.run_dir, run.cv_text, run.job = run_dir, orch.state.cv_text, orch.state.job
        with self.lock:
            if self.active():
                raise HTTPException(409, "Zaten çalışan bir süreç var, bitmesini bekleyin")
            self.runs[run.id] = run
        threading.Thread(target=self._work_resume, args=(run, orch, bus), daemon=True).start()
        return run

    def _work_resume(self, run: WebRun, orch: Orchestrator, bus: EventBus) -> None:
        try:
            orch.run()
        except (RunFailed, RunPaused):
            pass
        except Exception as e:
            bus.publish("run_failed", None, error=f"beklenmeyen hata ({type(e).__name__}: {e})")
        finally:
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


def create_app(provider, runs_dir: Path = Path("runs"), mode: str = "mock", lang: str = DEFAULT_LANG,
               memory_dir: Path | None = None) -> FastAPI:
    memory = LessonStore(memory_dir) if memory_dir else None
    manager = RunManager(runs_dir, provider, memory)
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
            "memory": memory is not None,
            "mock_answers": MOCK_ANSWERS if mode == "mock" else [],
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
            run = manager.start(tmp, files, run_lang, str(form.get("auto_yes")) == "1", str(form.get("pdf")) == "1")
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

    @app.get("/api/history")
    def history():
        return manager.history()

    @app.post("/api/replay")
    async def replay_run(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        if not isinstance(body, dict) or not isinstance(body.get("dir"), str):
            raise HTTPException(400, "dir gerekli")
        try:
            speed = float(1.0 if body.get("speed") is None else body["speed"])
        except (TypeError, ValueError):
            raise HTTPException(400, "speed bir sayı olmalı")
        upto = body.get("upto")
        if upto is not None and (not isinstance(upto, int) or isinstance(upto, bool) or upto < 0):
            raise HTTPException(400, "upto bir tam sayı olmalı")
        if not 0.1 <= speed <= 50:
            raise HTTPException(400, "speed 0.1 ile 50 arasında olmalı")
        return {"id": manager.start_replay(body["dir"], speed, bool(body.get("instant")), upto).id}

    @app.post("/api/interviews")
    async def start_interview(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        count = body.get("count", interview_mod.DEFAULT_COUNT) if isinstance(body, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("dir"), str):
            raise HTTPException(400, "dir gerekli")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= interview_mod.MAX_COUNT:
            raise HTTPException(400, f"count 1 ile {interview_mod.MAX_COUNT} arasında bir sayı olmalı")
        return {"id": manager.start_interview(body["dir"], count).id}

    @app.post("/api/runs/{run_id}/answer")
    async def answer_question(run_id: str, request: Request):
        run = get_run(run_id)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        action = body.get("action") if isinstance(body, dict) else None
        if action not in ("answer", "skip", "finish"):
            raise HTTPException(400, "action 'answer', 'skip' ya da 'finish' olmalı")
        text = str(body.get("text") or "").strip()
        if action == "answer" and not text:
            raise HTTPException(400, "Cevap boş olamaz")
        if len(text) > interview_mod.MAX_ANSWER_CHARS:
            raise HTTPException(400, "Cevap çok uzun")
        if not run.answer_open:
            raise HTTPException(409, "Şu anda bekleyen bir soru yok")
        run.answer = None if action == "finish" else (text if action == "answer" else "")
        run.answer_open = False
        run.answer_ready.set()
        return {"ok": True}

    @app.get("/api/paused")
    def paused():
        return manager.paused()

    @app.post("/api/resume")
    async def resume(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        name = body.get("dir") if isinstance(body, dict) else None
        if not isinstance(name, str):
            raise HTTPException(400, "dir gerekli")
        return {"id": manager.resume(name, bool(body.get("pdf"))).id}

    def need_memory() -> LessonStore:
        if memory is None:
            raise HTTPException(404, "Hafıza kapalı")
        return memory

    @app.get("/api/lessons")
    def lessons():
        try:
            return [l.__dict__ for l in need_memory().all()]
        except MemoryError_ as e:
            raise HTTPException(500, str(e))

    @app.delete("/api/lessons/{lesson_id}")
    def delete_lesson(lesson_id: str):
        try:
            if not need_memory().delete(lesson_id):
                raise HTTPException(404, "Böyle bir ders yok")
        except MemoryError_ as e:
            raise HTTPException(500, str(e))
        return {"ok": True}

    def candidates(run: WebRun) -> dict:
        path = run.run_dir / "work" / "lesson_candidates.json" if run.run_dir else None
        if path is None or not path.is_file():
            return {"accepted": [], "rejected": []}
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/runs/{run_id}/lessons")
    def run_lessons(run_id: str):
        run = get_run(run_id)
        need_memory()
        return {**candidates(run), "answered": run.lessons_answered}

    @app.post("/api/runs/{run_id}/lessons")
    async def answer_lessons(run_id: str, request: Request):
        """Nothing is saved unless the browser sends the indices the user clicked."""
        run = get_run(run_id)
        store = need_memory()
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "Geçersiz istek")
        accept = body.get("accept") if isinstance(body, dict) else None
        if not isinstance(accept, list) or not all(isinstance(i, int) for i in accept):
            raise HTTPException(400, "accept bir sayı listesi olmalı")
        if run.lessons_answered:
            raise HTTPException(409, "Bu çalıştırmanın dersleri zaten yanıtlandı")
        cands = candidates(run)["accepted"]
        saved, failed = [], []
        for i in dict.fromkeys(accept):
            if not 0 <= i < len(cands):
                raise HTTPException(400, "Geçersiz ders numarası")
            try:
                saved.append(store.add(cands[i]["agent"], cands[i]["text"]).__dict__)
            except ValueError as e:
                failed.append({"text": cands[i]["text"], "reason": str(e)})
            except MemoryError_ as e:
                raise HTTPException(500, str(e))
        run.lessons_answered = True
        return {"saved": saved, "failed": failed}

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
        media = ("text/plain; charset=utf-8" if path.suffix in (".md", ".txt", ".json", ".jsonl")
                 else "application/pdf" if path.suffix == ".pdf" else "application/octet-stream")
        headers = {"Content-Disposition": f'attachment; filename="{name}"'} if download else {}
        return FileResponse(path, media_type=media, headers=headers)

    app.mount("/static", Static(directory=STATIC), name="static")
    return app


def serve(provider, runs_dir: Path, mode: str, lang: str, port: int, open_browser: bool = True,
          memory_dir: Path | None = None) -> None:
    import socket

    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex((HOST, port)) == 0:
            raise OSError(f"{HOST}:{port} kullanımda. Başka bir port deneyin: career-crew web --port {port + 1}")
    app = create_app(provider, runs_dir, mode, lang, memory_dir)
    url = f"http://{HOST}:{port}"
    print(f"career-crew web ({mode} modu, yalnızca bu bilgisayardan erişilir): {url}")
    print("Durdurmak için Ctrl+C.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
