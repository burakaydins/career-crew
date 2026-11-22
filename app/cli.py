"""Terminal interface: `career-crew --ilan ilan.md --cv cv.md --mod mock`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from app import interview, replay
from app.events import Event, EventBus
from app.inputs import ACCEPTED, InputError, read_input
from app.memory import DEFAULT_DIR, LessonStore, MemoryError_
from app.orchestrator import Orchestrator, RunFailed, RunPaused, create_run_dir
from app.persist import StateError
from app.providers.base import ProviderError
from app.registry import DEFAULT_LANG, LANGUAGES, Registry
from app.skills import RunState

console = Console(highlight=False)

STATUS = {
    "analyze_job": "ilanı okuyor",
    "tailor_cv": "CV'yi uyarlıyor",
    "verify": "doğruluyor",
    "score": "puanlıyor",
    "write_letter": "ön yazıyı yazıyor",
    "prepare_interview": "mülakat sorularını hazırlıyor",
    "extract_lessons": "ders adaylarını çıkarıyor",
    "ask_question": "soruyu hazırlıyor",
    "evaluate_answer": "cevabı değerlendiriyor",
}

COLLAPSE_AFTER = 5  # a long list of code findings is shown as the first 3 plus a count
EXIT_PAUSED = 75  # EX_TEMPFAIL: not an error, run again later with --devam


def make_provider(mode: str, mock_delay: float):
    if mode == "mock":
        from app.providers.mock import MockProvider
        return MockProvider(delay=mock_delay)
    if mode == "claude-code":
        from app.providers.claude_code import ClaudeCodeProvider
        return ClaudeCodeProvider()
    from app.providers.api import ApiProvider
    return ApiProvider()


class Renderer:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def name(self, agent: str | None) -> str:
        if agent == "code":
            return "[bold white]🧮 Kod kontrolü[/]"
        card = self.registry.cards.get(agent or "")
        return f"[bold {card.color}]{card.displayName}[/]" if card else str(agent)

    def plain_name(self, agent: str | None) -> str:
        card = self.registry.cards.get(agent or "")
        return card.displayName if card else str(agent)

    def __call__(self, e: Event) -> None:
        d = e.data
        match e.type:
            case "run_started":
                console.rule(f"[bold]career-crew[/] · mod: {d['provider']}")
                console.print(f"[dim]Çalıştırma klasörü: {d['run_dir']}[/]")
            case "run_resumed":
                console.rule(f"[bold]career-crew[/] · devam · mod: {d['provider']}")
                console.print(f"[dim]{d['skipped']} adım zaten tamamdı, atlanıyor. Klasör: {d['run_dir']}[/]")
            case "run_paused":
                console.print(f"{self.name(e.agent)}: [yellow]limit doldu, süreç duraklatıldı[/]")
            case "pdf":
                console.print(f"{self.name('code')}: PDF hazır: {', '.join(d['files'])}")
            case "lessons_proposed":
                pass  # shown after the run, together with the question
            case "loop_iteration":
                console.rule(f"[dim]CV turu {d['iteration']}/{d['max']}[/]", style="dim")
            case "task_started":
                console.print(f"[dim]… {self.plain_name(e.agent)} {STATUS.get(d['skill'], 'çalışıyor')}[/]")
            case "agent_message":
                console.print(f"{self.name(e.agent)}: {d['text']}")
            case "checks":
                errs = d["errors"]
                head = "Sorun yok." if not errs else f"{len(errs)} sorun:"
                console.print(f"{self.name('code')}: {head} ATS %{d['ats_before']} → %{d['ats_after']}")
                shown = errs if len(errs) <= COLLAPSE_AFTER else errs[:3]
                for msg in shown:
                    console.print(f"   [red]✗[/] {msg}")
                if len(shown) < len(errs):
                    console.print(f"   [dim]… ve {len(errs) - len(shown)} sorun daha (tamamı events.jsonl içinde, düzeltmesi CV Yazarı'nda)[/]")
                for msg in d["warnings"][:COLLAPSE_AFTER]:
                    console.print(f"   [yellow]![/] {msg}")
                if len(d["warnings"]) > COLLAPSE_AFTER:
                    console.print(f"   [dim]… ve {len(d['warnings']) - COLLAPSE_AFTER} uyarı daha[/]")
            case "warning":
                console.print(f"[yellow]⚠️  {d['text']}[/]")
            case "task_failed":
                console.print(f"{self.name(e.agent)}: [red]hata: {d['error']}[/]")
            case "loop_done":
                if d["converged"]:
                    console.print(f"[green]✓ CV {d['iteration']}. turda hedefe ulaştı.[/]")
            case "run_finished":
                console.rule("[bold green]Bitti[/]")
                console.print(f"📦 Çıktılar: {d['output']}")
                out = Path(d["output"])
                for f in sorted(p.name for p in out.iterdir()) if out.is_dir() else []:
                    console.print(f"   • {f}")
                console.print("[dim]Yapay zekâ çıktıları hatalı olabilir. Başvurmadan önce her şeyi kendiniz kontrol edin.[/]")


def show_job(job: dict) -> None:
    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_row("[bold]Pozisyon[/]", job.get("title", ""))
    t.add_row("[bold]Şirket[/]", job.get("company", ""))
    t.add_row("[bold]Seviye[/]", job.get("level", ""))
    t.add_row("[bold]Zorunlu[/]", ", ".join(job.get("required_skills", [])))
    t.add_row("[bold]Tercih[/]", ", ".join(job.get("preferred_skills", [])))
    t.add_row("[bold]Anahtar kelimeler[/]", ", ".join(job.get("keywords", [])))
    console.print(t)


def make_ask(auto_yes: bool):
    def ask(gate: str, state: RunState) -> str | None:
        show_job(state.job)
        if auto_yes or not sys.stdin.isatty():
            console.print("[dim]🙋 İlan okuması otomatik onaylandı.[/]")
            return None
        if Confirm.ask("🙋 İlan doğru okundu mu?", default=True):
            return None
        return Prompt.ask("Neyi düzeltelim?")
    return ask


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="career-crew", description="Çok ajanlı iş başvurusu asistanı.")
    p.add_argument("--ilan", type=Path, help="İş ilanı (.md, .txt, .pdf, .docx, .png, .jpg)")
    p.add_argument("--cv", type=Path, help="CV (.md, .txt, .pdf, .docx, .png, .jpg)")
    p.add_argument("--devam", type=Path, metavar="KLASÖR", help="Duraklayan ya da yarıda kalan çalıştırmayı sürdür (runs/...)")
    p.add_argument("--pdf", action="store_true", help="CV ve ön yazıyı PDF olarak da üret")
    p.add_argument("--hafiza", type=Path, default=DEFAULT_DIR, help="Derslerin tutulduğu klasör (varsayılan: memory/)")
    p.add_argument("--mod", default="mock", choices=["mock", "claude-code", "api"], help="Model sağlayıcısı (varsayılan: mock)")
    p.add_argument("--dil", default=DEFAULT_LANG, choices=LANGUAGES, help="Ajan promptlarının dili (varsayılan: tr)")
    p.add_argument("--runs", default=Path("runs"), type=Path, help="Çalıştırma klasörlerinin yeri (varsayılan: runs/)")
    p.add_argument("--evet", action="store_true", help="İlan okuma onayını sorma")
    p.add_argument("--hizli", action="store_true", help="mock modunda bekleme yapma")
    args = p.parse_args(argv)
    if not args.devam and not (args.ilan and args.cv):
        p.error("--ilan ve --cv gerekli (ya da duraklayan bir çalıştırma için --devam KLASÖR)")
    return args


def parse_web_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="career-crew web", description="Yerel web arayüzü (yalnızca 127.0.0.1).")
    p.add_argument("--port", type=int, default=8765, help="Port (varsayılan: 8765)")
    p.add_argument("--mod", default="mock", choices=["mock", "claude-code", "api"], help="Model sağlayıcısı (varsayılan: mock)")
    p.add_argument("--dil", default=DEFAULT_LANG, choices=LANGUAGES, help="Varsayılan prompt dili (arayüzden değiştirilebilir)")
    p.add_argument("--runs", default=Path("runs"), type=Path, help="Çalıştırma klasörlerinin yeri (varsayılan: runs/)")
    p.add_argument("--hizli", action="store_true", help="mock modunda bekleme yapma")
    p.add_argument("--hafiza", type=Path, default=DEFAULT_DIR, help="Derslerin tutulduğu klasör (varsayılan: memory/)")
    p.add_argument("--acma", action="store_true", help="Tarayıcıyı kendiliğinden açma")
    return p.parse_args(argv)


def web_main(argv: list[str]) -> int:
    args = parse_web_args(argv)
    try:
        provider = make_provider(args.mod, 0.0 if args.hizli else 0.6)
    except ProviderError as e:
        console.print(f"[red]{e}[/]")
        return 2
    from app.web.server import serve

    try:
        serve(provider, args.runs, args.mod, args.dil, args.port, open_browser=not args.acma, memory_dir=args.hafiza)
    except OSError as e:
        console.print(f"[red]{e}[/]")
        return 2
    except KeyboardInterrupt:
        pass
    return 0


AGENT_LABEL = {"cv_writer": "CV Yazarı", "letter_writer": "Mektup Yazarı", "interviewer": "Mülakatçı"}


def review_lessons(state: RunState, store: LessonStore) -> None:
    """Asks about each lesson candidate. Never saves without an answer: --evet does not apply,
    and without a terminal nothing is saved."""
    for r in state.lesson_rejected:
        console.print(f"[dim]Ders adayı elendi ({r['reason']}): {r['text']}[/]")
    if not state.lesson_candidates:
        return
    if not sys.stdin.isatty():
        console.print("[dim]Ders adayları var ama onay için etkileşimli terminal gerekiyor, hiçbiri kaydedilmedi. "
                      f"Adaylar: {state.work / 'lesson_candidates.json'}[/]")
        return
    console.rule("[bold]Hafıza[/]", style="dim")
    console.print("[dim]Kabul ettiğiniz dersler sonraki çalıştırmalarda ilgili ajana eklenir. Yalnızca bu bilgisayarda saklanır.[/]")
    for c in state.lesson_candidates:
        if Confirm.ask(f"{AGENT_LABEL.get(c['agent'], c['agent'])}: \"{c['text']}\" kaydedilsin mi?", default=False):
            try:
                lesson = store.add(c["agent"], c["text"])
                console.print(f"[green]Kaydedildi[/] (id: {lesson.id})")
            except ValueError as e:
                console.print(f"[yellow]Kaydedilemedi: {e}[/]")


def lessons_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="career-crew ders", description="Kayıtlı dersleri yönet.")
    p.add_argument("--hafiza", type=Path, default=DEFAULT_DIR, help="Derslerin tutulduğu klasör (varsayılan: memory/)")
    sub = p.add_subparsers(dest="komut", required=True)
    sub.add_parser("listele", help="Kayıtlı dersleri listele")
    rm = sub.add_parser("sil", help="Bir dersi sil")
    rm.add_argument("id")
    args = p.parse_args(argv)
    store = LessonStore(args.hafiza)
    try:
        if args.komut == "listele":
            lessons = store.all()
            if not lessons:
                console.print("Kayıtlı ders yok.")
            for l in lessons:
                console.print(f"[bold]{l.id}[/]  {AGENT_LABEL.get(l.agent, l.agent)}: {l.text}  [dim]({l.created})[/]")
            return 0
        if store.delete(args.id):
            console.print("Silindi.")
            return 0
        console.print(f"[red]Böyle bir ders yok: {args.id}[/]")
        return 1
    except MemoryError_ as e:
        console.print(f"[red]{e}[/]")
        return 2


def replay_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="career-crew replay", description="Bitmiş bir çalıştırmayı terminalde yeniden oynat.")
    p.add_argument("klasor", type=Path, metavar="KLASÖR", help="Çalıştırma klasörü (runs/...)")
    p.add_argument("--hiz", type=float, default=1.0, help="Hız çarpanı, örn. 2 iki kat hızlı (varsayılan: 1)")
    p.add_argument("--aninda", action="store_true", help="Beklemeden hepsini hemen göster")
    args = p.parse_args(argv)
    if args.hiz <= 0:
        console.print("[red]--hiz sıfırdan büyük olmalı[/]")
        return 2
    try:
        events = replay.load_events(args.klasor)
        renderer = Renderer(Registry(lang=replay.run_language(args.klasor)))
        for _ in replay.play(events, renderer, args.hiz, args.aninda):
            pass
    except (replay.ReplayError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/]")
        return 2
    except KeyboardInterrupt:
        console.print("\n[yellow]Oynatma durduruldu.[/]")
        return 130
    return 0


class InterviewRenderer(Renderer):
    """Same renderer as a normal run, plus the mock-interview events."""

    def __call__(self, e: Event) -> None:
        d = e.data
        match e.type:
            case "interview_started":
                console.rule(f"[bold]Deneme mülakatı[/] · {d['total']} soru · {d['title']}")
                console.print("[dim]Cevabını yaz ve Enter'a bas. Soruyu geçmek için boş bırak, bitirmek için /bitir yaz.[/]")
            case "interview_question":
                console.print(f"[dim]Soru {d['n']}/{d['total']}[/]")
            case "interview_evaluation":
                color = {"strong": "green", "ok": "yellow", "weak": "red"}[d["verdict"]]
                console.print(f"   [{color}]● {interview.LABELS['tr']['v'][d['verdict']]}[/]")
                for f in d["flags"]:
                    console.print(f"   [red]✗ CV'de yok:[/] {f['claim']}" + (f" [dim]({f['why']})[/]" if f["why"] else ""))
                for c in d["code_flags"]:
                    console.print(f"   [yellow]! {c}[/]")
                if d["framing"]:
                    console.print(f"   [green]Dürüst çerçeve:[/] {d['framing']}")
            case "interview_finished":
                console.rule("[bold green]Mülakat bitti[/]")
            case "interview_report":
                console.print(f"📝 Geri bildirim: {d['path']}")
            case _:
                super().__call__(e)


def interview_main(argv: list[str]) -> int:
    from rich.markup import escape

    p = argparse.ArgumentParser(prog="career-crew mulakat", description="Bitmiş bir çalıştırmanın CV'sine göre deneme mülakatı yap.")
    p.add_argument("klasor", type=Path, metavar="KLASÖR", help="Çalıştırma klasörü (runs/...)")
    p.add_argument("--mod", default="mock", choices=["mock", "claude-code", "api"], help="Model sağlayıcısı (varsayılan: mock)")
    p.add_argument("--soru", type=int, default=interview.DEFAULT_COUNT, help=f"Soru sayısı (varsayılan: {interview.DEFAULT_COUNT}, en fazla {interview.MAX_COUNT})")
    p.add_argument("--betik", action="store_true", help="mock modunda hazır cevapları kullan (demo ve test için)")
    args = p.parse_args(argv)
    if args.soru < 1:
        console.print("[red]--soru en az 1 olmalı[/]")
        return 2
    scripted = args.mod == "mock" and (args.betik or not sys.stdin.isatty())
    if not scripted and not sys.stdin.isatty():
        console.print("[red]Etkileşimli bir terminal gerekli: cevapları sen yazacaksın.[/]")
        return 2
    try:
        provider = make_provider(args.mod, 0.0)
    except ProviderError as e:
        console.print(f"[red]{e}[/]")
        return 2
    bus = EventBus()
    try:
        session = interview.open_session(args.klasor, provider, bus, args.soru)
    except (interview.InterviewError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/]")
        return 2
    bus.subscribe(InterviewRenderer(session.orch.registry))

    def get_answer(n: int, question: str) -> str | None:
        if scripted:
            from app.providers.mock import MOCK_ANSWERS
            text = MOCK_ANSWERS[(n - 1) % len(MOCK_ANSWERS)]
            console.print(f"[bold]Sen:[/] {escape(text)}")
            return text
        answer = Prompt.ask("[bold]Sen[/]", default="", show_default=False)
        return None if answer.strip().lower() == "/bitir" else answer

    try:
        path = interview.run(session, get_answer)
    except RunPaused as e:
        console.print(f"[yellow]Limit doldu, mülakat durdu ({e}). Cevapladıkların kaydedildi.[/]")
        return EXIT_PAUSED
    except RunFailed as e:
        console.print(f"[red]Mülakat durdu: {e}[/]")
        return 1
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]İptal edildi.[/]")
        return 130
    if path is None:
        console.print("Hiç soru cevaplanmadı, geri bildirim yazılmadı.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "mulakat":
        return interview_main(argv[1:])
    if argv and argv[0] == "replay":
        return replay_main(argv[1:])
    if argv and argv[0] == "web":
        return web_main(argv[1:])
    if argv and argv[0] == "ders":
        return lessons_main(argv[1:])
    args = parse_args(argv)
    try:
        provider = make_provider(args.mod, 0.0 if args.hizli else 0.6)
    except ProviderError as e:
        console.print(f"[red]{e}[/]")
        return 2

    store = LessonStore(args.hafiza)
    try:
        store.all()  # fail early on a damaged lessons file
    except MemoryError_ as e:
        console.print(f"[red]{e}[/]")
        return 2

    bus = EventBus()
    if args.devam:
        if not args.devam.is_dir():
            console.print(f"[red]Klasör bulunamadı: {args.devam}[/]")
            return 2
        try:
            orch = Orchestrator.resume(args.devam, provider, make_ask(args.evet), bus, memory=store, pdf=args.pdf)
        except StateError as e:
            console.print(f"[red]{e}[/]")
            return 2
        bus.subscribe(Renderer(orch.registry))
        run_dir = args.devam
    else:
        texts = {}
        for name, f in (("ilan", args.ilan), ("cv", args.cv)):
            if not f.is_file():
                console.print(f"[red]Dosya bulunamadı: {f}[/]")
                return 2
            if f.suffix.lower() not in ACCEPTED:
                console.print(f"[red]Desteklenmeyen dosya türü: {f.name} (desteklenenler: {', '.join(ACCEPTED)})[/]")
                return 2
            try:
                texts[name] = read_input(f, provider, name)
            except InputError as e:
                console.print(f"[red]{e}[/]")
                return 2

        registry = Registry(lang=args.dil)
        bus.subscribe(Renderer(registry))
        run_dir = create_run_dir(args.runs, args.ilan, args.cv)
        # Keep the extracted text next to the originals: it is what the agents and checks saw.
        for name, f in (("ilan", args.ilan), ("cv", args.cv)):
            if f.suffix.lower() not in (".md", ".txt"):
                (run_dir / "inputs" / f"{name}_metin.md").write_text(texts[name], encoding="utf-8")
        orch = Orchestrator(
            provider=provider,
            run_dir=run_dir,
            job_text=texts["ilan"],
            cv_text=texts["cv"],
            ask=make_ask(args.evet),
            bus=bus,
            registry=registry,
            memory=store,
            pdf=args.pdf,
        )
    try:
        state = orch.run()
    except RunPaused as e:
        console.print(f"[yellow]Limit doldu, süreç duraklatıldı ({e}).[/]")
        console.print("Durum kaydedildi. Limit yenilenince şu komutla kaldığı yerden devam edin:")
        console.print(f"  career-crew --devam {run_dir} --mod {args.mod}")
        return EXIT_PAUSED
    except RunFailed as e:
        console.print(f"[red]Süreç durdu: {e}[/]")
        console.print(f"[dim]Kayıt: {run_dir / 'events.jsonl'}. Adımlar kayıtlı, şunu deneyebilirsiniz: career-crew --devam {run_dir} --mod {args.mod}[/]")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]İptal edildi.[/]")
        console.print(f"[dim]Kaldığı yerden devam için: career-crew --devam {run_dir} --mod {args.mod}[/]")
        return 130
    review_lessons(state, store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
