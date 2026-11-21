"""Terminal interface: `career-crew --ilan ilan.md --cv cv.md --mod mock`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from app.events import Event, EventBus
from app.orchestrator import Orchestrator, RunFailed, create_run_dir
from app.providers.base import ProviderError
from app.registry import Registry
from app.skills import RunState

console = Console(highlight=False)

STATUS = {
    "analyze_job": "ilanı okuyor",
    "tailor_cv": "CV'yi uyarlıyor",
    "verify": "doğruluyor",
    "score": "puanlıyor",
    "write_letter": "ön yazıyı yazıyor",
    "prepare_interview": "mülakat sorularını hazırlıyor",
}


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

    def __call__(self, e: Event) -> None:
        d = e.data
        match e.type:
            case "run_started":
                console.rule(f"[bold]career-crew[/] · mod: {d['provider']}")
                console.print(f"[dim]Çalıştırma klasörü: {d['run_dir']}[/]")
            case "loop_iteration":
                console.rule(f"[dim]CV turu {d['iteration']}/{d['max']}[/]", style="dim")
            case "task_started":
                console.print(f"[dim]… {self.registry[e.agent].displayName} {STATUS.get(d['skill'], 'çalışıyor')}[/]")
            case "agent_message":
                console.print(f"{self.name(e.agent)}: {d['text']}")
            case "checks":
                errs = d["errors"]
                head = "Sorun yok." if not errs else f"{len(errs)} sorun:"
                console.print(f"{self.name('code')}: {head} ATS %{d['ats_before']} → %{d['ats_after']}")
                for msg in errs:
                    console.print(f"   [red]✗[/] {msg}")
                for msg in d["warnings"]:
                    console.print(f"   [yellow]![/] {msg}")
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
                for f in ("cv.md", "cover_letter.md", "interview.md", "report.md"):
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
    p.add_argument("--ilan", required=True, type=Path, help="İş ilanı (.md ya da .txt)")
    p.add_argument("--cv", required=True, type=Path, help="CV (.md ya da .txt)")
    p.add_argument("--mod", default="mock", choices=["mock", "claude-code", "api"], help="Model sağlayıcısı (varsayılan: mock)")
    p.add_argument("--runs", default=Path("runs"), type=Path, help="Çalıştırma klasörlerinin yeri (varsayılan: runs/)")
    p.add_argument("--evet", action="store_true", help="İlan okuma onayını sorma")
    p.add_argument("--hizli", action="store_true", help="mock modunda bekleme yapma")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for f in (args.ilan, args.cv):
        if not f.is_file():
            console.print(f"[red]Dosya bulunamadı: {f}[/]")
            return 2
        if f.suffix.lower() not in (".md", ".txt"):
            console.print(f"[red]Şimdilik yalnızca .md ve .txt destekleniyor: {f}[/]")
            return 2

    try:
        provider = make_provider(args.mod, 0.0 if args.hizli else 0.6)
    except ProviderError as e:
        console.print(f"[red]{e}[/]")
        return 2

    registry = Registry()
    bus = EventBus()
    bus.subscribe(Renderer(registry))
    run_dir = create_run_dir(args.runs, args.ilan, args.cv)
    orch = Orchestrator(
        provider=provider,
        run_dir=run_dir,
        job_text=args.ilan.read_text(encoding="utf-8"),
        cv_text=args.cv.read_text(encoding="utf-8"),
        ask=make_ask(args.evet),
        bus=bus,
        registry=registry,
    )
    try:
        orch.run()
    except RunFailed as e:
        console.print(f"[red]Süreç durdu: {e}[/]")
        console.print(f"[dim]Kayıt: {run_dir / 'events.jsonl'}[/]")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]İptal edildi.[/]")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
