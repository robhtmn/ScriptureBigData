"""Load the Strong's Hebrew and Greek lexicons (OpenScriptures JSON-in-JS).

Each dictionary is a JavaScript file assigning one big object literal. We isolate
the object and parse it as JSON. Entries provide the original-script lemma
headword, a transliteration, a short gloss (KJV usage) and a fuller definition —
used for interlinear glosses, word studies, and to attach Strong's numbers to
Greek tokens that lack them in their source.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from ..model import LexEntry
from . import sources

_ASSIGN = re.compile(r"Dictionary\s*=\s*\{")


def _extract_object(js: str) -> dict:
    m = _ASSIGN.search(js)
    start = js.index("{", m.start()) if m else js.index("{")
    end = js.rindex("}")
    return json.loads(js[start:end + 1])


def _short_gloss(strongs_def: str, kjv_def: str) -> str:
    """A concise interlinear gloss (a few words), drawn preferentially from the
    core definition rather than the long KJV usage list."""
    src = (strongs_def or kjv_def or "").strip()
    src = re.sub(r"^-+\s*", "", src)                       # strip leading "--"
    src = re.sub(r"\[idiom\]|\[phrase\]|\(.*?\)", "", src)  # drop asides
    seg = re.split(r"[;:]", src)[0]
    seg = seg.replace("i.e.", "").replace("  ", " ").strip(" .,")
    words = seg.split()
    if len(words) > 6:
        seg = " ".join(words[:6])
    return seg.strip(" .,")


def _full_definition(strongs_def: str, kjv_def: str) -> str:
    parts = []
    if strongs_def and strongs_def.strip():
        parts.append(strongs_def.strip())
    if kjv_def and kjv_def.strip():
        parts.append("KJV: " + re.sub(r"^-+\s*", "", kjv_def.strip()))
    return " — ".join(parts)


def parse_dictionary(js: str, language: str) -> Iterator[LexEntry]:
    data = _extract_object(js)
    for strongs, entry in data.items():
        sdef = entry.get("strongs_def", "") or ""
        kjv = entry.get("kjv_def", "") or ""
        yield LexEntry(
            strongs=strongs,
            lemma=entry.get("lemma", ""),
            translit=entry.get("translit") or entry.get("xlit", ""),
            pronunciation=entry.get("pron", ""),
            gloss=_short_gloss(sdef, kjv),
            definition=_full_definition(sdef, kjv),
            language=language,
        )


def ingest(languages: list[str] | None = None, progress=None) -> Iterator[LexEntry]:
    for language in (languages or ["hebrew", "greek"]):
        if progress:
            progress(f"Strong's {language} lexicon")
        js = sources.fetch_text(sources.strongs_url(language))
        yield from parse_dictionary(js, language)
