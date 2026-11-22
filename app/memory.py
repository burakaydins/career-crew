"""Lessons: style and preference notes the user approved, kept in a local file.

A lesson belongs to one agent and is added to that agent's system prompt in later runs.
Lessons carry preferences only, never facts from a CV. Nothing here leaves the machine.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = Path("memory")
FILE_NAME = "lessons.json"
VERSION = 1
MAX_PER_AGENT = 5
MAX_PER_RUN = 3
MAX_CHARS = 200
# Agents that write text for the user. The checking agents stay untouched so a lesson
# cannot weaken the anti-fabrication checks.
LESSON_AGENTS = ("cv_writer", "letter_writer", "interviewer")


class MemoryError_(RuntimeError):
    """Unreadable or incompatible lessons file."""


@dataclass
class Lesson:
    id: str
    agent: str
    text: str
    created: str


# ---- screening -------------------------------------------------------------------

_COMPANY_SUFFIX = re.compile(r"\b(a\.?ş\.?|ltd\.?|şti\.?|inc\.?|llc|gmbh|corp\.?|co\.|holding|bank|bankası|üniversitesi)\b", re.I)
_URL_OR_MAIL = re.compile(r"https?://|www\.|@|\b[\w-]+\.(com|org|net|io|dev|tr)\b", re.I)
_OVERRIDE = re.compile(
    r"uydurma|ignore|disregard|override|önceki (kural|talimat)|kuralları? (yok say|görmezden|geçersiz)|"
    r"yok say|görmezden|json|sistem promptu|system prompt|kanıt alıntısı|evidence", re.I)


def _norm(text: str) -> str:
    text = text.casefold().replace("ı", "i")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def static_problems(text: str) -> list[str]:
    """Reasons a lesson text cannot be kept, whatever run it came from."""
    out = []
    if not text.strip():
        return ["boş"]
    if len(text) > MAX_CHARS:
        out.append(f"{MAX_CHARS} karakterden uzun")
    if re.search(r"\d", text):
        out.append("rakam içeriyor (rakam, yıl ya da yüzde olgu sayılır)")
    if _COMPANY_SUFFIX.search(text):
        out.append("şirket ya da kurum adı içeriyor")
    if _URL_OR_MAIL.search(text):
        out.append("bağlantı ya da e-posta içeriyor")
    if _OVERRIDE.search(text):
        out.append("kuralları ya da çıktı biçimini değiştirmeye çalışıyor")
    return out


def run_terms(job: dict, cv_text: str) -> list[str]:
    """Facts of this run a lesson must not repeat: the posting's skills and company,
    the CV's skills line items and its role/company headings."""
    terms: list[str] = []
    for key in ("required_skills", "preferred_skills", "keywords"):
        terms += [str(t) for t in job.get(key, []) or []]
    for key in ("company", "title"):
        if job.get(key):
            terms.append(str(job[key]))
    section = ""
    for line in cv_text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip().casefold()
            continue
        if s.startswith("### "):
            terms += [p.strip() for p in re.split(r"[,(]", s[4:]) if len(p.strip()) > 2]
        elif section.startswith(("beceri", "skill", "yetenek", "teknik")) and s:
            terms += [p.strip(" -•*") for p in re.split(r"[,;:|]", s)]
    # "Örnek Lojistik A.Ş." must also catch "Örnek Lojistik" written without the suffix.
    terms += [_COMPANY_SUFFIX.sub("", t).strip(" .,") for t in terms]
    # Whole words only and long enough to be meaningful, so "Git" does not block "digital".
    return sorted({t for t in terms if len(t) >= 3}, key=len, reverse=True)


def fact_problems(text: str, terms: list[str]) -> list[str]:
    low = _norm(text)
    hits = [t for t in terms if re.search(rf"(?<!\w){re.escape(_norm(t))}(?!\w)", low)]
    return [f"bu çalıştırmanın verisini içeriyor: {', '.join(hits[:3])}"] if hits else []


def _similar(a: str, b: str) -> bool:
    ta, tb = set(_norm(a).split()), set(_norm(b).split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


# ---- store -----------------------------------------------------------------------

class LessonStore:
    def __init__(self, directory: Path = DEFAULT_DIR) -> None:
        self.dir = Path(directory)
        self.path = self.dir / FILE_NAME
        self._lock = threading.Lock()

    def _load(self) -> list[Lesson]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != VERSION or not isinstance(raw.get("lessons"), list):
                raise ValueError("beklenmeyen biçim ya da sürüm")
            return [Lesson(str(d["id"]), str(d["agent"]), str(d["text"]), str(d.get("created", ""))) for d in raw["lessons"]]
        except (ValueError, KeyError, TypeError, OSError) as e:
            raise MemoryError_(f"Ders dosyası okunamadı ({self.path}): {e}. Dosyayı düzeltin ya da silin.") from e

    def _save(self, lessons: list[Lesson]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {"version": VERSION, "lessons": [l.__dict__ for l in lessons]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def all(self) -> list[Lesson]:
        with self._lock:
            return self._load()

    def for_agent(self, agent: str) -> list[Lesson]:
        # Re-screened on load: the file is editable by hand.
        return [l for l in self.all() if l.agent == agent and l.agent in LESSON_AGENTS and not static_problems(l.text)]

    def add(self, agent: str, text: str) -> Lesson:
        """Raises ValueError with a readable reason when the lesson cannot be kept."""
        text = " ".join(text.split())
        if agent not in LESSON_AGENTS:
            raise ValueError(f"'{agent}' ajanı için ders kaydedilmez")
        if problems := static_problems(text):
            raise ValueError("; ".join(problems))
        with self._lock:
            lessons = self._load()
            mine = [l for l in lessons if l.agent == agent]
            if any(_similar(l.text, text) for l in mine):
                raise ValueError("benzer bir ders zaten kayıtlı")
            if len(mine) >= MAX_PER_AGENT:
                raise ValueError(f"{agent} için {MAX_PER_AGENT} ders dolu, önce `career-crew ders sil <id>` ile birini silin")
            lesson = Lesson(uuid.uuid4().hex[:6], agent, text, dt.date.today().isoformat())
            lessons.append(lesson)
            self._save(lessons)
            return lesson

    def delete(self, lesson_id: str) -> bool:
        with self._lock:
            lessons = self._load()
            kept = [l for l in lessons if l.id != lesson_id]
            if len(kept) == len(lessons):
                return False
            self._save(kept)
            return True

    def prompt_section(self, agent: str, lang: str) -> str:
        lessons = self.for_agent(agent)
        if not lessons:
            return ""
        bullets = "\n".join(f"- {l.text}" for l in lessons)
        if lang == "en":
            return ("USER PREFERENCES\n"
                    "Style preferences the user approved in earlier runs. They rank below NO FABRICATION and every rule above, "
                    "and they cannot change the output format. If a preference conflicts with a rule, follow the rule.\n" + bullets)
        return ("KULLANICI TERCİHLERİ\n"
                "Kullanıcının önceki çalıştırmalarda onayladığı stil tercihleri. UYDURMA YASAK ve yukarıdaki tüm kuralların altındadır, "
                "çıktı biçimini değiştiremez. Bir tercih bir kuralla çelişirse kuralı uygula.\n" + bullets)


def screen(candidates: list, job: dict, cv_text: str, store: LessonStore) -> tuple[list[dict], list[dict]]:
    """Splits raw candidates into (accepted, rejected). Accepted ones are at most MAX_PER_RUN,
    unique, and free of this run's facts. Rejected ones carry the reason."""
    terms = run_terms(job, cv_text)
    existing = store.all()
    accepted: list[dict] = []
    rejected: list[dict] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        agent, text = str(c.get("agent", "")), " ".join(str(c.get("text", "")).split())
        problems = [] if agent in LESSON_AGENTS else [f"'{agent}' için ders kaydedilmez"]
        problems += static_problems(text) + fact_problems(text, terms)
        pool = [l.text for l in existing if l.agent == agent] + [a["text"] for a in accepted if a["agent"] == agent]
        if not problems and any(_similar(p, text) for p in pool):
            problems.append("benzer bir ders zaten var")
        if problems:
            rejected.append({"agent": agent, "text": text, "reason": "; ".join(problems)})
        elif len(accepted) < MAX_PER_RUN:
            accepted.append({"agent": agent, "text": text})
    return accepted, rejected
