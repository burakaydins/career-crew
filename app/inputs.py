"""Reads CVs and job postings from .md, .txt, .pdf and .docx into Markdown-like text.

Checks work on bullets ("- ") and "## " headings, so the readers map list items
and headings to that form where the source format says what they are.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.providers.base import ProviderError

SUPPORTED = (".md", ".txt", ".pdf", ".docx")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
ACCEPTED = SUPPORTED + IMAGE_SUFFIXES
MAX_BYTES = 10 * 1024 * 1024
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}
MIN_WORDS = 20
BULLET_CHARS = "•●▪◦‣∙·–—"
# "*" is a bullet only before a space: "**Şirket:**" is bold text, not a list item.
_BULLET_LINE = re.compile(rf"^\s*(?:[{re.escape(BULLET_CHARS)}]\s*|\*\s+)")


class InputError(ValueError):
    pass


class NeedsVision(InputError):
    """The file holds no readable text (a picture or a scanned PDF): a model has to look at it."""


def check_upload(name: str, size: int) -> str:
    """Validate an uploaded file by name and size. Returns the lowercase suffix."""
    suffix = Path(name).suffix.lower()
    if suffix not in ACCEPTED:
        raise InputError(f"Desteklenmeyen dosya türü: {Path(name).name} (desteklenenler: {', '.join(ACCEPTED)})")
    if size > MAX_BYTES:
        raise InputError(f"{Path(name).name} çok büyük ({size / 1024 / 1024:.1f} MB), sınır {MAX_BYTES // 1024 // 1024} MB")
    if size == 0:
        raise InputError(f"{Path(name).name} boş")
    return suffix


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        raise NeedsVision(f"{path.name} bir görsel, metne çevrilmesi gerekiyor")
    if suffix not in SUPPORTED:
        raise InputError(f"Desteklenmeyen dosya türü: {path.name} (desteklenenler: {', '.join(ACCEPTED)})")
    if suffix in (".md", ".txt"):
        text = _read_text(path)
    elif suffix == ".pdf":
        text = _read_pdf(path)
    else:
        text = _read_docx(path)
    text = normalize_bullets(text)
    if suffix in (".pdf", ".txt"):
        text = promote_headings(text)
    text = text.strip()
    if len(text.split()) < MIN_WORDS:
        if suffix == ".pdf":
            raise NeedsVision(f"{path.name} içinden yeterli metin çıkmadı, taranmış bir PDF olabilir")
        raise InputError(f"{path.name} içinden yeterli metin çıkmadı")
    return text + "\n"


def read_input(path: Path, provider, kind: str) -> str:
    """Like read_document, but pictures and scanned PDFs are read by the provider's model.
    `kind` is "ilan" or "cv". The transcript is what the agents and checks treat as the source text."""
    try:
        return read_document(path)
    except NeedsVision:
        transcribe = getattr(provider, "transcribe", None)
        if transcribe is None:
            raise
        try:
            text = transcribe(MEDIA_TYPES[path.suffix.lower()], path.read_bytes(), kind)
        except ProviderError as e:
            raise InputError(f"{path.name} okunamadı: {e}") from e
        text = normalize_bullets(text).strip()
        if len(text.split()) < MIN_WORDS:
            raise InputError(f"{path.name} içinden yeterli metin okunamadı")
        return text + "\n"


def normalize_bullets(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if _BULLET_LINE.match(line) and not line.lstrip().startswith("- "):
            line = "- " + _BULLET_LINE.sub("", line, count=1)
        lines.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


SECTION_NAMES = {
    "ozet", "profil", "hakkimda", "kariyer hedefi", "deneyim", "is deneyimi", "egitim",
    "beceriler", "yetenekler", "yetkinlikler", "teknik beceriler", "projeler", "sertifikalar",
    "diller", "yabanci diller", "referanslar", "summary", "profile", "about", "experience",
    "work experience", "professional experience", "education", "skills", "technical skills",
    "projects", "certifications", "languages", "references",
}


def promote_headings(text: str) -> str:
    """PDF and plain text lose heading markup. Turn lines that are only a known
    section name ("Deneyim", "SKILLS") into "## " headings. Text that already has
    Markdown headings is left alone."""
    from app.checks.text import normalize

    if re.search(r"^##\s", text, re.MULTILINE):
        return text
    out = []
    for line in text.splitlines():
        if normalize(line).rstrip(":") in SECTION_NAMES:
            line = "## " + line.strip().rstrip(":")
        out.append(line)
    return "\n".join(out)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InputError(f"{path.name} okunamadı")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise InputError(f"{path.name} şifreli, şifresiz bir kopyasını verin")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as e:
        raise InputError(f"{path.name} PDF olarak okunamadı: {e}") from e
    return "\n\n".join(pages)


def _read_docx(path: Path) -> str:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(path)
    except PackageNotFoundError as e:
        raise InputError(f"{path.name} DOCX olarak okunamadı") from e

    lines = []
    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            lines.append("")
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style == "title":
            lines.append(f"# {text}")
        elif style.startswith("heading"):
            level = 2 if style in ("heading 1", "heading") else 3
            lines.append(f"{'#' * level} {text}")
        elif "list" in style or p._p.pPr is not None and p._p.pPr.numPr is not None:
            lines.append(f"- {text}")
        else:
            lines.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(lines)
