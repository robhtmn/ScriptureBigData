"""Ingest the Hebrew/Aramaic Old Testament from the OpenScriptures Hebrew Bible
(morphhb / Westminster Leningrad Codex) OSIS XML.

Each ``<w>`` element carries the pointed surface text (morphemes joined by
``/``), a ``lemma`` attribute (Strong's-number based, with prefix letters), and
a ``morph`` attribute in the OSHB scheme. We keep the Strong's number and the
decoded morphology; the pointed Hebrew *lemma* headword is filled in later from
the Strong's lexicon during the build.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator

from ..model import Token
from ..morphology import parse_hebrew_morph
from . import sources

_OSIS_ID = re.compile(r"^([\w]+)\.(\d+)\.(\d+)$")
_INT = re.compile(r"\d+")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _strongs_from_lemma(lemma: str) -> str:
    """Extract the head Strong's number from an OSHB lemma like ``b/7225`` or
    ``1254 a`` and format as ``H####``."""
    if not lemma:
        return ""
    m = _INT.search(lemma)
    return f"H{int(m.group())}" if m else ""


def parse_osis(xml_bytes: bytes, edition: str = "WLC") -> Iterator[Token]:
    """Yield :class:`Token` objects from one morphhb OSIS book file."""
    root = ET.fromstring(xml_bytes)
    for verse_el in root.iter():
        if _localname(verse_el.tag) != "verse":
            continue
        osis_id = verse_el.get("osisID", "")
        m = _OSIS_ID.match(osis_id)
        if not m:
            continue  # milestone/eID markers
        book, chapter, verse = m.group(1), int(m.group(2)), int(m.group(3))
        position = 0
        for w in verse_el:
            if _localname(w.tag) != "w":
                continue  # skip <seg> punctuation, notes, etc.
            surface = "".join(w.itertext())
            if not surface.strip():
                continue
            surface = surface.replace("/", "")  # join morphemes for display
            position += 1
            lemma_attr = w.get("lemma", "")
            morph_attr = w.get("morph", "")
            strongs = _strongs_from_lemma(lemma_attr)
            morph = parse_hebrew_morph(morph_attr)
            yield Token(
                edition=edition,
                language=morph.language or "hebrew",
                book=book, chapter=chapter, verse=verse, position=position,
                surface=surface,
                lemma="",  # filled from lexicon during build
                strongs=strongs,
                morph_code=morph_attr,
                morph_desc=morph.description,
                pos=morph.pos,
            )


def ingest_book(book: str, edition: str = "WLC") -> list[Token]:
    """Fetch and parse a single OT book by OSIS id (e.g. ``"Gen"``)."""
    data = sources.fetch(sources.morphhb_url(book))
    return list(parse_osis(data, edition=edition))


def ingest(books: list[str] | None = None, edition: str = "WLC",
           progress=None) -> Iterator[Token]:
    """Yield tokens for the requested OT books (default: all)."""
    for book in (books or sources.MORPHHB_BOOKS):
        if progress:
            progress(f"Hebrew OT: {book}")
        try:
            yield from ingest_book(book, edition=edition)
        except Exception as exc:  # skip a book that fails rather than abort all
            if progress:
                progress(f"  ! skipped {book}: {exc}")
