"""Records a mock run and renders it as an animated GIF for the README.

    python scripts/make_demo_gif.py docs/demo.gif

macOS only (uses the Menlo and Apple Color Emoji system fonts). Needs Pillow.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rich.cells import cell_len
from rich.console import Console
from rich.segment import Segment

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.cli as cli  # noqa: E402
from app.events import EventBus  # noqa: E402
from app.orchestrator import Orchestrator, create_run_dir  # noqa: E402
from app.providers.mock import MockProvider  # noqa: E402
from app.registry import Registry  # noqa: E402

COLS, ROWS = 84, 30
FONT_SIZE, LINE_H, PAD, BAR = 15, 21, 18, 34
BG, FG = (24, 24, 32), (220, 220, 228)
MONO = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", FONT_SIZE)
MONO_BOLD = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", FONT_SIZE, index=1)
EMOJI = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 160)
CELL_W = MONO.getlength("M")
ANSI = {  # rich standard colors -> RGB
    "red": (239, 83, 80), "green": (102, 187, 106), "yellow": (255, 202, 40),
    "white": (235, 235, 240), "bright_white": (255, 255, 255),
}
_emoji_cache: dict[str, Image.Image] = {}


def emoji_image(ch: str, size: int) -> Image.Image:
    if ch not in _emoji_cache:
        img = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, 0), ch, font=EMOJI, embedded_color=True)
        _emoji_cache[ch] = img.crop(img.getbbox() or (0, 0, 1, 1)).resize((size, size), Image.LANCZOS)
    return _emoji_cache[ch]


def is_emoji(ch: str) -> bool:
    # Agent icons. "✍" and "🛡" are emoji only with U+FE0F, so rich counts them as one cell.
    return ord(ch) >= 0x1F000 or ch in "✍🛡"


def color_of(style) -> tuple[int, int, int]:
    if style is None or style.color is None:
        return FG
    c = style.color
    if c.triplet is not None:
        return tuple(c.triplet)
    if c.name in ANSI:
        return ANSI[c.name]
    if style.dim:
        return (130, 130, 145)
    return tuple(c.get_truecolor())


def render(lines: list[list[Segment]]) -> Image.Image:
    w = int(PAD * 2 + COLS * CELL_W)
    h = BAR + PAD * 2 + ROWS * LINE_H
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, BAR), fill=(38, 38, 50))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((14 + i * 22, 11, 26 + i * 22, 23), fill=c)
    d.text((w / 2, BAR / 2), "career-crew --mod mock", font=MONO, fill=(150, 150, 165), anchor="mm")
    for row, line in enumerate(lines[-ROWS:]):
        y = BAR + PAD + row * LINE_H
        col = 0
        for seg in line:
            style = seg.style
            fill = (130, 130, 145) if style is not None and style.dim and style.color is None else color_of(style)
            font = MONO_BOLD if style is not None and style.bold else MONO
            for ch in seg.text:
                x = PAD + col * CELL_W
                if ch == "️":  # emoji presentation selector, drawn with the emoji
                    continue
                if is_emoji(ch):
                    e = emoji_image(ch, FONT_SIZE + 3)
                    img.paste(e, (int(x), y), e)
                    col += 2
                else:
                    d.text((x, y), ch, font=font, fill=fill)
                    col += cell_len(ch)
    return img


def main(out: Path) -> None:
    buf = io.StringIO()
    console = Console(file=buf, record=True, width=COLS, force_terminal=True, color_system="truecolor")
    cli.console = console  # the renderer and gate print through this module-level console

    frames: list[tuple[Image.Image, int]] = []

    def snapshot(event) -> None:
        lines = list(Segment.split_and_crop_lines(console._record_buffer, COLS, pad=False))
        pause = {"loop_iteration": 600, "checks": 2200, "agent_message": 1300, "run_finished": 6000}
        frames.append((render(lines), pause.get(event.type, 700)))

    registry = Registry()
    bus = EventBus()
    bus.subscribe(cli.Renderer(registry))
    bus.subscribe(snapshot)
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)  # so the recording shows "runs/…" instead of a temp path
        run_dir = create_run_dir(Path("runs"), ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
        Orchestrator(
            provider=MockProvider(),
            run_dir=run_dir,
            job_text=(ROOT / "examples/ilan.md").read_text(encoding="utf-8"),
            cv_text=(ROOT / "examples/cv.md").read_text(encoding="utf-8"),
            ask=cli.make_ask(auto_yes=True),
            bus=bus,
            registry=registry,
        ).run()

    images = [f for f, _ in frames]
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(out, save_all=True, append_images=images[1:], duration=[d for _, d in frames],
                   loop=0, optimize=True)
    print(f"{out} · {len(images)} kare · {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/demo.gif").resolve())
