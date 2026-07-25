"""Normalised data records shared across ingesters, storage and the engine.

The :class:`Token` is the atom of the whole system: one word (or, for Hebrew,
one word possibly composed of several morphemes) in one edition, carrying its
original-language surface form plus every piece of linguistic metadata we know
about it. Ingesters emit ``Token`` objects; the database stores them; search and
analysis read them back.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Text normalisation                                                          #
# --------------------------------------------------------------------------- #

# Hebrew points/accents live in these Unicode blocks; removing them yields the
# bare consonantal text that most people search by.
_HEBREW_MARKS = tuple(chr(c) for c in range(0x0591, 0x05C8))  # accents + points
_HEBREW_MARK_SET = set(_HEBREW_MARKS)


def strip_hebrew_points(text: str) -> str:
    """Return consonantal Hebrew: vowel points and cantillation removed."""
    out = [ch for ch in text if ch not in _HEBREW_MARK_SET]
    # Also drop the maqaf/sof-pasuq punctuation joins for cleaner tokens.
    return "".join(out).replace("־", " ").replace("׃", "").strip()


def strip_greek_accents(text: str) -> str:
    """Return unaccented, lowercase Greek (diacritics removed)."""
    decomposed = unicodedata.normalize("NFD", text)
    out = [ch for ch in decomposed if not unicodedata.combining(ch)]
    return unicodedata.normalize("NFC", "".join(out)).lower()


def normalize_for_search(text: str, language: str) -> str:
    """Produce the search-normalised form of a surface word for its language."""
    if not text:
        return ""
    if language in ("hebrew", "aramaic"):
        return strip_hebrew_points(text)
    if language == "greek":
        return strip_greek_accents(text)
    return text.lower()


# --------------------------------------------------------------------------- #
# Records                                                                      #
# --------------------------------------------------------------------------- #

@dataclass
class Token:
    """One word/morpheme cluster of one edition, fully annotated."""

    edition: str                 # e.g. "WLC", "SBLGNT", "LXX-Rahlfs"
    language: str                # "hebrew" | "aramaic" | "greek"
    book: str                    # OSIS id, e.g. "Gen"
    chapter: int
    verse: int
    position: int                # 1-based word index within the verse

    surface: str                 # original text with vowels/accents
    norm: str = ""               # search-normalised surface (no points/accents)
    lemma: str = ""              # dictionary form (original script)
    lemma_norm: str = ""         # search-normalised lemma
    strongs: str = ""            # e.g. "H430", "G2532" (empty if unknown)
    morph_code: str = ""         # raw morphology code from the source
    morph_desc: str = ""         # human-readable parsing
    pos: str = ""                # coarse part of speech
    gloss: str = ""              # short English gloss
    translit: str = ""           # transliteration (optional)

    def __post_init__(self) -> None:
        if not self.norm:
            self.norm = normalize_for_search(self.surface, self.language)
        if self.lemma and not self.lemma_norm:
            self.lemma_norm = normalize_for_search(self.lemma, self.language)


@dataclass
class Verse:
    """A verse's worth of tokens in one edition."""

    edition: str
    language: str
    book: str
    chapter: int
    verse: int
    tokens: list[Token] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(t.surface for t in self.tokens)

    @property
    def gloss(self) -> str:
        return " ".join(t.gloss for t in self.tokens if t.gloss)

    @property
    def ref(self) -> str:
        return f"{self.book} {self.chapter}:{self.verse}"


@dataclass
class SearchHit:
    """A single match returned by the search engine."""

    edition: str
    language: str
    book: str
    chapter: int
    verse: int
    position: int
    surface: str
    lemma: str
    strongs: str
    gloss: str
    morph_desc: str
    verse_text: str = ""          # full surface text of the containing verse
    book_order: int = 0

    @property
    def reference(self) -> str:
        from .canon import format_reference
        return format_reference(self.book, self.chapter, self.verse)


@dataclass
class LexEntry:
    """A lexicon (Strong's) entry."""

    strongs: str                 # "H430" / "G26"
    lemma: str                   # original-script headword
    translit: str = ""
    pronunciation: str = ""
    gloss: str = ""              # short definition / KJV usage
    definition: str = ""         # fuller definition
    language: str = ""           # "hebrew" | "greek"
