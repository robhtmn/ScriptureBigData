"""Canon: books of Scripture, their ordering, and reference parsing.

This module is the single source of truth for *which* books exist and how they
are named and ordered. Editions (Hebrew OT, Greek NT, Septuagint) reference
books by their OSIS abbreviation so the same book (e.g. Genesis) can appear in
more than one edition and still be aligned.

Testament codes:

* ``OT`` — Hebrew/Aramaic Old Testament (the Protestant/Jewish canon)
* ``NT`` — Greek New Testament
* ``DC`` — deuterocanonical / apocryphal books that appear in the Septuagint

The book list is data, not behaviour: to support additional books (e.g. more of
the Septuagint) you add rows here and the rest of the system follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    """Metadata for a single book of Scripture."""

    order: int          # global canonical order (1-based)
    osis: str           # OSIS abbreviation, the stable identifier used everywhere
    name: str           # human-readable English name
    testament: str      # "OT" | "NT" | "DC"


# --- Old Testament (Hebrew/Aramaic), OSIS order -----------------------------
_OT = [
    ("Gen", "Genesis"), ("Exod", "Exodus"), ("Lev", "Leviticus"),
    ("Num", "Numbers"), ("Deut", "Deuteronomy"), ("Josh", "Joshua"),
    ("Judg", "Judges"), ("Ruth", "Ruth"), ("1Sam", "1 Samuel"),
    ("2Sam", "2 Samuel"), ("1Kgs", "1 Kings"), ("2Kgs", "2 Kings"),
    ("1Chr", "1 Chronicles"), ("2Chr", "2 Chronicles"), ("Ezra", "Ezra"),
    ("Neh", "Nehemiah"), ("Esth", "Esther"), ("Job", "Job"),
    ("Ps", "Psalms"), ("Prov", "Proverbs"), ("Eccl", "Ecclesiastes"),
    ("Song", "Song of Songs"), ("Isa", "Isaiah"), ("Jer", "Jeremiah"),
    ("Lam", "Lamentations"), ("Ezek", "Ezekiel"), ("Dan", "Daniel"),
    ("Hos", "Hosea"), ("Joel", "Joel"), ("Amos", "Amos"),
    ("Obad", "Obadiah"), ("Jonah", "Jonah"), ("Mic", "Micah"),
    ("Nah", "Nahum"), ("Hab", "Habakkuk"), ("Zeph", "Zephaniah"),
    ("Hag", "Haggai"), ("Zech", "Zechariah"), ("Mal", "Malachi"),
]

# --- New Testament (Greek), canonical order ---------------------------------
_NT = [
    ("Matt", "Matthew"), ("Mark", "Mark"), ("Luke", "Luke"),
    ("John", "John"), ("Acts", "Acts"), ("Rom", "Romans"),
    ("1Cor", "1 Corinthians"), ("2Cor", "2 Corinthians"), ("Gal", "Galatians"),
    ("Eph", "Ephesians"), ("Phil", "Philippians"), ("Col", "Colossians"),
    ("1Thess", "1 Thessalonians"), ("2Thess", "2 Thessalonians"),
    ("1Tim", "1 Timothy"), ("2Tim", "2 Timothy"), ("Titus", "Titus"),
    ("Phlm", "Philemon"), ("Heb", "Hebrews"), ("Jas", "James"),
    ("1Pet", "1 Peter"), ("2Pet", "2 Peter"), ("1John", "1 John"),
    ("2John", "2 John"), ("3John", "3 John"), ("Jude", "Jude"),
    ("Rev", "Revelation"),
]

# --- Deuterocanonical / Septuagint-only books -------------------------------
# These appear in the Greek Septuagint but not the Hebrew canon. OSIS-style
# abbreviations are used where they exist.
_DC = [
    ("1Esd", "1 Esdras"), ("Tob", "Tobit"), ("Jdt", "Judith"),
    ("Wis", "Wisdom of Solomon"), ("Sir", "Sirach (Ecclesiasticus)"),
    ("Bar", "Baruch"), ("EpJer", "Letter of Jeremiah"),
    ("1Macc", "1 Maccabees"), ("2Macc", "2 Maccabees"),
    ("3Macc", "3 Maccabees"), ("4Macc", "4 Maccabees"),
    ("PrMan", "Prayer of Manasseh"), ("Odes", "Odes"),
    ("PssSol", "Psalms of Solomon"), ("Sus", "Susanna"),
    ("Bel", "Bel and the Dragon"), ("AddEsth", "Additions to Esther"),
    ("AddDan", "Additions to Daniel"),
]


def _build_books() -> list[Book]:
    books: list[Book] = []
    order = 1
    for osis, name in _OT:
        books.append(Book(order, osis, name, "OT"))
        order += 1
    for osis, name in _NT:
        books.append(Book(order, osis, name, "NT"))
        order += 1
    for osis, name in _DC:
        books.append(Book(order, osis, name, "DC"))
        order += 1
    return books


BOOKS: list[Book] = _build_books()
BY_OSIS: dict[str, Book] = {b.osis: b for b in BOOKS}
BY_OSIS_LOWER: dict[str, Book] = {b.osis.lower(): b for b in BOOKS}


# --- Source-specific book maps ----------------------------------------------

# MorphGNT / SBLGNT encode the book as a two-digit number 01..27 inside the
# BBCCVV reference. 01 = Matthew.
NT_NUMBER_TO_OSIS: dict[int, str] = {i + 1: osis for i, (osis, _n) in enumerate(_NT)}

# morphhb file names use OSIS-ish stems already, but a couple differ from the
# OSIS abbreviations we standardise on.
MORPHHB_FILE_TO_OSIS: dict[str, str] = {
    "Song": "Song",   # Song of Songs
    "Ps": "Ps",
}

# The Septuagint source (eliranwong/LXX-Rahlfs-1935) uses these abbreviations in
# its versification. Map them onto our OSIS identifiers. Books that share a
# Hebrew counterpart reuse that book's OSIS id so Hebrew<->Greek alignment works;
# Septuagint-only books map onto the deuterocanonical entries above.
LXX_ABBREV_TO_OSIS: dict[str, str] = {
    "Gen": "Gen", "Exod": "Exod", "Lev": "Lev", "Num": "Num", "Deut": "Deut",
    "Josh": "Josh", "Judg": "Judg", "Ruth": "Ruth",
    "1Sam": "1Sam", "2Sam": "2Sam", "1Kgs": "1Kgs", "2Kgs": "2Kgs",
    "1Chr": "1Chr", "2Chr": "2Chr",
    "1Esdr": "1Esd", "2Esdr": "Ezra",   # 2 Esdras (LXX) ≈ Ezra-Nehemiah
    "Ezra": "Ezra", "Neh": "Neh",
    "Esth": "Esth", "Job": "Job", "Ps": "Ps", "Prov": "Prov", "Eccl": "Eccl",
    "Song": "Song", "Isa": "Isa", "Jer": "Jer", "Lam": "Lam", "Ezek": "Ezek",
    "Dan": "Dan", "Hos": "Hos", "Joel": "Joel", "Amos": "Amos", "Obad": "Obad",
    "Jonah": "Jonah", "Mic": "Mic", "Nah": "Nah", "Hab": "Hab", "Zeph": "Zeph",
    "Hag": "Hag", "Zech": "Zech", "Mal": "Mal",
    # Deuterocanonical
    "Jdt": "Jdt", "TobBA": "Tob", "TobS": "Tob", "Tob": "Tob",
    "Wis": "Wis", "Sir": "Sir", "Bar": "Bar", "EpJer": "EpJer",
    "1Macc": "1Macc", "2Macc": "2Macc", "3Macc": "3Macc", "4Macc": "4Macc",
    "PrMan": "PrMan", "Odes": "Odes", "PsSol": "PssSol", "PssSol": "PssSol",
    "Sus": "Sus", "Bel": "Bel",
    "1Kgds": "1Sam", "2Kgds": "2Sam", "3Kgds": "1Kgs", "4Kgds": "2Kgs",
    "1Chron": "1Chr", "2Chron": "2Chr",
}


# --- Name normalisation & reference parsing ---------------------------------

# Common human aliases -> OSIS. Kept small; the OSIS ids and full names are the
# primary interface.
_ALIASES: dict[str, str] = {
    "genesis": "Gen", "gen": "Gen",
    "exodus": "Exod", "exod": "Exod", "exo": "Exod", "ex": "Exod",
    "leviticus": "Lev", "lev": "Lev",
    "numbers": "Num", "num": "Num",
    "deuteronomy": "Deut", "deut": "Deut", "deu": "Deut",
    "psalm": "Ps", "psalms": "Ps", "pss": "Ps", "ps": "Ps",
    "proverbs": "Prov", "prov": "Prov", "pro": "Prov",
    "isaiah": "Isa", "isa": "Isa",
    "matthew": "Matt", "matt": "Matt", "mat": "Matt", "mt": "Matt",
    "mark": "Mark", "mrk": "Mark", "mk": "Mark",
    "luke": "Luke", "luk": "Luke", "lk": "Luke",
    "john": "John", "jhn": "John", "jn": "John",
    "acts": "Acts", "act": "Acts",
    "romans": "Rom", "rom": "Rom",
    "revelation": "Rev", "rev": "Rev", "apocalypse": "Rev",
    "songofsongs": "Song", "song": "Song", "canticles": "Song",
    "ecclesiastes": "Eccl", "eccl": "Eccl", "qoheleth": "Eccl",
}


def resolve_book(name: str) -> Book | None:
    """Resolve a book name/abbreviation/OSIS id to a :class:`Book`.

    Accepts OSIS ids ("Gen"), full names ("Genesis"), and common aliases,
    case-insensitively and ignoring spaces.
    """
    if not name:
        return None
    raw = name.strip()
    if raw in BY_OSIS:
        return BY_OSIS[raw]
    key = raw.lower().replace(" ", "").replace(".", "")
    if key in BY_OSIS_LOWER:
        return BY_OSIS_LOWER[key]
    if key in _ALIASES:
        return BY_OSIS[_ALIASES[key]]
    # Full-name match
    for b in BOOKS:
        if b.name.lower().replace(" ", "") == key:
            return b
    return None


_REF_RE = re.compile(
    r"^\s*(?P<book>(?:[1-4]\s*)?[A-Za-z][A-Za-z ]*?)\s*"
    r"(?P<chapter>\d+)?\s*[:.]?\s*(?P<verse>\d+)?\s*"
    r"(?:[-–]\s*(?P<end>\d+))?\s*$"
)


def parse_reference(text: str) -> "ReferenceQuery | None":
    """Parse a human reference like ``"John 3:16"`` or ``"Gen 1"`` or
    ``"Ps 23:1-6"`` into a :class:`ReferenceQuery`. Returns ``None`` if the book
    cannot be resolved.
    """
    m = _REF_RE.match(text or "")
    if not m:
        return None
    book = resolve_book(m.group("book"))
    if book is None:
        return None
    chapter = int(m.group("chapter")) if m.group("chapter") else None
    verse = int(m.group("verse")) if m.group("verse") else None
    end = int(m.group("end")) if m.group("end") else None
    return ReferenceQuery(book=book.osis, chapter=chapter, verse=verse, verse_end=end)


@dataclass(frozen=True)
class ReferenceQuery:
    """A parsed reference range used to filter the corpus."""

    book: str
    chapter: int | None = None
    verse: int | None = None
    verse_end: int | None = None

    def label(self) -> str:
        b = BY_OSIS.get(self.book)
        name = b.name if b else self.book
        if self.chapter is None:
            return name
        if self.verse is None:
            return f"{name} {self.chapter}"
        if self.verse_end and self.verse_end != self.verse:
            return f"{name} {self.chapter}:{self.verse}-{self.verse_end}"
        return f"{name} {self.chapter}:{self.verse}"


def book_order(osis: str) -> int:
    b = BY_OSIS.get(osis)
    return b.order if b else 9999


def format_reference(osis: str, chapter: int, verse: int) -> str:
    b = BY_OSIS.get(osis)
    name = b.name if b else osis
    return f"{name} {chapter}:{verse}"
