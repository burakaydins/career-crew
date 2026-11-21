"""Text normalization shared by all checks."""

from __future__ import annotations

import re
import unicodedata

_KEEP = re.compile(r"[^0-9a-z+#%./\s-]")
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, fold Turkish and other diacritics, drop punctuation, collapse spaces.

    "İ", "I" and "ı" all fold to "i" so Turkish and English casing match.
    """
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)  # decimal comma: "3,5" -> "3.5"
    text = text.replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("'", " ").replace("’", " ")
    text = _KEEP.sub(" ", text)
    text = re.sub(r"(?<![0-9])[./-]|[./-](?![0-9a-z])", " ", text)
    return _SPACE.sub(" ", text).strip()


def contains_term(text: str, term: str) -> bool:
    """Whole-word match of a (possibly multi-word) term in normalized text."""
    t = normalize(term)
    if not t:
        return False
    return re.search(rf"(?<![0-9a-z+#]){re.escape(t)}(?![0-9a-z+#])", normalize(text)) is not None
