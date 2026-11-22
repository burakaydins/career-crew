"""Markdown subset to PDF: headings, bullets, **bold**, *italic*, paragraphs.

Uses fpdf2 with DejaVu Sans embedded (app/assets/fonts, license included), so Turkish
letters render and can be read back from the text layer.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from fpdf import FPDF
from fontTools.ttLib import TTFont

FONTS = Path(__file__).parent / "assets" / "fonts"
FAMILY = "DejaVu"
ACCENT = (31, 78, 140)
GRAY = (95, 95, 95)
MAX_PAGES = {"cv": 2, "letter": 1}
SIZES = {"cv": (10.0, 9.5, 9.0, 8.5), "letter": (11.0, 10.5, 10.0, 9.5)}

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")


@lru_cache(maxsize=1)
def _glyphs() -> frozenset[int]:
    return frozenset(TTFont(FONTS / "DejaVuSans.ttf").getBestCmap())


def _clean(text: str) -> str:
    """Drops characters the font has no glyph for (emoji) instead of printing boxes."""
    text = text.replace("\t", "    ").replace(" ", " ")
    return "".join(c for c in text if ord(c) in _glyphs() or c == "\n")


def _segments(text: str) -> list[tuple[str, str]]:
    out = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], "B"))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append((part[1:-1], "I"))
        else:
            out.append((part, ""))
    return out


class _Doc(FPDF):
    pass


def _build(md: str, kind: str, size: float) -> FPDF:
    pdf = _Doc(format="A4", unit="mm")
    pdf.set_auto_page_break(True, margin=14)
    pdf.set_margins(18, 15, 18)
    for style, name in (("", "DejaVuSans.ttf"), ("B", "DejaVuSans-Bold.ttf"), ("I", "DejaVuSans-Oblique.ttf")):
        pdf.add_font(FAMILY, style, str(FONTS / name))
    pdf.set_creator("career-crew")
    pdf.add_page()
    line = size * 0.5  # line height in mm for the body size
    base_x = pdf.l_margin

    def write(text: str, bold: bool = False, color=(0, 0, 0), s: float = size, h: float | None = None) -> None:
        pdf.set_text_color(*color)
        for chunk, style in _segments(text):
            pdf.set_font(FAMILY, "B" if bold else style, s)
            pdf.write(h or line, chunk)

    first_h1 = True
    after_h1 = False
    for raw in _clean(md).splitlines():
        s = raw.rstrip()
        if not s.strip() or re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", s):
            pdf.ln(line * 0.45)
            continue
        pdf.set_x(base_x)
        if m := re.match(r"^#\s+(.*)", s):
            write(m.group(1), bold=True, color=ACCENT, s=size * 2.0, h=size * 0.95)
            pdf.ln(size * 0.95)
            first_h1, after_h1 = False, True
            continue
        if m := re.match(r"^##\s+(.*)", s):
            pdf.ln(line * 0.7)
            write(m.group(1), bold=True, color=ACCENT, s=size * 1.2, h=line * 1.3)
            pdf.ln(line * 1.3)
            y = pdf.get_y()
            pdf.set_draw_color(*ACCENT)
            pdf.set_line_width(0.25)
            pdf.line(base_x, y, pdf.w - pdf.r_margin, y)
            pdf.ln(line * 0.35)
            continue
        if m := re.match(r"^###+\s+(.*)", s):
            pdf.ln(line * 0.3)
            write(m.group(1), bold=True, s=size * 1.05)
            pdf.ln(line * 1.05)
            continue
        if m := _BULLET.match(s):
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(FAMILY, "", size)
            pdf.cell(4.5, line, "•")
            pdf.set_left_margin(base_x + 4.5)
            pdf.set_x(base_x + 4.5)
            write(m.group(1))
            pdf.ln(line)
            pdf.set_left_margin(base_x)
            continue
        # Contact line right under the name stays small and gray.
        if after_h1:
            write(s, color=GRAY, s=size * 0.95)
            pdf.ln(line)
            after_h1 = False
            continue
        write(s)
        pdf.ln(line * (1.0 if kind == "cv" else 1.15))
    return pdf


def render(md: str, path: Path, kind: str = "cv") -> int:
    """Writes the PDF and returns its page count. Shrinks the type until it fits the page budget."""
    pdf = None
    for size in SIZES[kind]:
        pdf = _build(md, kind, size)
        if pdf.page_no() <= MAX_PAGES[kind]:
            break
    pdf.output(str(path))
    return pdf.page_no()


def render_outputs(output: Path) -> list[str]:
    """cv.md and cover_letter.md in the output folder become PDFs next to them."""
    made = []
    for md_name, kind in (("cv.md", "cv"), ("cover_letter.md", "letter")):
        src = output / md_name
        if src.is_file():
            target = src.with_suffix(".pdf")
            render(src.read_text(encoding="utf-8"), target, kind)
            made.append(target.name)
    return made
